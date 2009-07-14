#!/usr/bin/env python
#<!-- coding=UTF-8 -->
from __future__ import absolute_import
from __future__ import with_statement

import os
import urllib
import datetime
import time
import random
import hashlib
import itertools
import simplejson

import numpy 

import webify
from webify.templates.helpers import html
from webify.controllers import webargs
import markdown

app = webify.defaults.app()

@app.subapp(path='/')
@webify.urlable()
def index(req, p):
    csv_location = req.settings[u'csv_location']
    files = [unicode(f) 
                for f in os.listdir(csv_location) if not f.endswith('json')]
    with html.ul(p):
       for file in files:
        p(html.li(html.a(view_csv.url(file), file)))

import csv
import StringIO

def csv_data_to_table(data):
    reader = csv.reader(StringIO.StringIO(data))
    rows = []
    for line in reader:
        rows.append([c.decode('utf8') for c in line])
    return rows

def extract_features(table):
    first_row = table[0]
    features = [r.strip(' \r\n') for r in first_row[1:]]
    return features

def extract_items(table):
    items = [row[0].strip(' \r\n') for row in table[1:]]
    return items

def extract_raw_data(table):
    rows = table[1:]
    data = [row[1:] for row in rows]
    return data

@app.subapp()
@webify.urlable()
def new_properties(req, p):
    data = simplejson.loads(req.params[u'data'])
    short_code = unicode(data[u'short_code'])
    assert(short_code_valid(short_code))

    properties = data[u'properties']

    csv_location = req.settings[u'csv_location']
    table, features, items = read_table(csv_location, short_code)

    cleaners_names = properties[u'cleaners']
    assert(len(cleaners_names) == len(features))
    save_cleaners(csv_location, short_code, cleaners_names)
    cleaners = load_cleaners(csv_location, short_code)

    filter_names = properties[u'filters']
    assert(len(filter_names) == len(features))
    save_filters(csv_location, short_code, filter_names)

    raw_data = extract_raw_data(table)
    clean_data = clean_raw_data(raw_data, cleaners, filter_names)

    template_clean_data(p, clean_data, features, items, cleaners_names, filter_names)

import simplejson
@app.subapp()
@webify.urlable()
def new_data(req, p):
    data = simplejson.loads(req.params[u'data'])
    short_code = unicode(data[u'short_code'])
    assert(short_code_valid(short_code))

    csv_location = req.settings[u'csv_location']
    table, features, items = read_table(csv_location, short_code)
    cleaners_names = load_cleaners_names(csv_location, short_code) or [u'mean'] * len(features)
    cleaners = [cleaner_funcs[c] for c in cleaners_names]
    filter_names = load_filter_names(csv_location, short_code) or [[]] * len(features)
    normalized_data = normalize_table(table, cleaners, filter_names)
    
    equation = {}
    for f in data[u'features']:
        assert(f.startswith('feature_'))
         # Negate everything because it's position from top
        feature_id = int(f[8:])
        value = data[u'features'][f]
        if value is not None:
            equation[feature_id] = float(value)

    rankings, normalized_equation = calculate_rankings(normalized_data, equation)

    template_rankings(p, items, rankings)
    template_equation(p, normalized_equation, features)

def read_table(csv_location, short_code):
    assert(short_code_valid(short_code))
    with open(os.path.join(csv_location, short_code), 'r') as f:
        table = csv_data_to_table(f.read())
    features = extract_features(table)
    items = extract_items(table)
    return table, features, items

def normalize_table(table, cleaners, filter_names):
    raw_data = extract_raw_data(table)
    clean_data = clean_raw_data(raw_data, cleaners, filter_names)
    normalized_data = normalize(clean_data)
    return normalized_data

@app.subapp()
@webargs.RemainingUrlableAppWrapper()
def view_csv(req, p, short_code):
    csv_location = req.settings[u'csv_location']
    table, features, items = read_table(csv_location, short_code)
    cleaners_names = load_cleaners_names(csv_location, short_code) or [u'mean'] * len(features)
    cleaners = [cleaner_funcs[c] for c in cleaners_names]
    filter_names = load_filter_names(csv_location, short_code) or [[]] * len(features)
    raw_data = extract_raw_data(table)
    clean_data = clean_raw_data(raw_data, cleaners, filter_names)
    normalized_data = normalize(clean_data)

    equation = {}
    for i,count in itertools.izip(xrange(len(features)), 
                                  itertools.count()):
        equation[i] = 10 - (count / 2.0 + 0.5)
    
    rankings, normalized_equation = calculate_rankings(normalized_data, equation)

    with html.head(p):
        p(html.title('%s | AutoRanker' % short_code))
        #p(u'<script src="http://www.google.com/jsapi"></script>')
        p(u'<script src="http://ajax.googleapis.com/ajax/libs/jquery/1.3.2/jquery.min.js"></script>')
        p(u'<script src="http://ajax.googleapis.com/ajax/libs/jqueryui/1.7.2/jquery-ui.min.js"></script>')
        p(u'<script src="http://www.json.org/json2.js"></script>')
        with html.script_block(p):
            #p(u'google.load("jquery", "1.3.2");google.load("jqueryui", "1.7.2");')
            p(u'''
               var features = {};
               jQuery(function($) {
                    var send_new_data = function() {
                        var short_code = $('#short_code').val();
                        $.ajax({
                            type: 'POST',
                            url: "''' + new_data.url() + '''",
                            data: {'data':JSON.stringify({'short_code':short_code,
                                   'features':features})},
                            dataType: 'html',
                            success: function(msg) {
                                $('#rankings').html(msg);
                            }});
                    };
                    $('#all_features div').draggable({
                        cursor: 'pointer',
                        opacity: 0.55,
                        distance: 0,
                        zIndex: 2700
                    });
                    $('#all_features').droppable({
                        tolerance: 'fit',
                        hoverClass: 'drophover'
                    });
                    $('#features').droppable({
                        drop: function(event, ui) { 
                            var p = ui.offset;
                            var name = ui.helper.attr('id');
                            features[name] = p.top;
                            send_new_data();
                        },
                        out: function(event, ui) {
                            var name = ui.helper.attr('id');
                            features[name] = null;
                            send_new_data();
                        },
                        tolerance: 'fit',
                        hoverClass: 'drophover'
                    });
                    var get_filters = function() {
                        var filters = [];
                        var f = $('.filters');
                        for(var i=0;i<f.length;i++) {
                            var inputs = f.eq(i).children('input');
                            var current_filters = [];
                            for(var j=0;j<inputs.length;j++) {
                                var current_input = inputs.eq(j);
                                if(current_input .attr('checked')) {
                                    current_filters[current_filters.length] = current_input.attr('name');
                                }
                            }
                            filters[i] = current_filters;
                        }
                        return filters;
                    };
                    var get_cleaners = function() {
                        var cleaners = [];
                        var c = $('.cleaners');
                        for(var i=0;i<c.length;i++) {
                            cleaners[i] = c.eq(i).val();
                        }
                        return cleaners;
                    };
                    var send_properties = function() {
                        var short_code = $('#short_code').val();
                        var properties = {'cleaners':get_cleaners(),
                                          'filters':get_filters()};
                        $.ajax({
                            type: 'POST',
                            url: "''' + new_properties.url() + '''",
                            data: {'data':JSON.stringify({'short_code':short_code,
                                   'properties':properties})},
                            dataType: 'html',
                            success: function(msg) {
                                $('#full_data').html(msg);
                                send_new_data();
                            }});
                    };
                    $('.cleaners').live('change', function(){send_properties();});
                    $('#rerank').live('click', function(){send_new_data();});
                    $('.filters input').live('change', function(){
                        send_properties();
                    });

                    /* #TODO: jperla: this doesn't work for some reason */
                    $("#loading").bind("ajaxStart", function(){
                        $(this).show();
                    }).bind("ajaxStop", function(){
                        $(this).hide();
                    });
               });
            ''')
        p(u'''
            <style type="text/css">
                #features {
                    height:30em;
                    background-color:blue;
                    width:20em;
                }
                #features.drophover {
                    background-color:#1589FF;
                }
                #all_features.drophover {
                    background-color:pink;
                }
                #all_features {
                    background-color:red;
                    padding:10px;
                }
                #all_features div {
                    background-color:#FFCC44;
                    border:1px solid black;
                    padding:5px;
                    cursor:pointer;
                    /* 
                    margin:10 0 10 0;
                    */
                }
                #features div {
                    background-color:yellow;
                }
            </style>
        ''')
    p(u'<input type="hidden" id="short_code" value="%s" />' % short_code)
    with html.div(p, {u'id':u'full_data'}):
        template_clean_data(p, clean_data, features, items, cleaners_names, filter_names)
    p(html.br())
    with html.table(p):
        with html.tr(p):
            with html.td_block(p, {'width':'67%', 'valign':'top'}):
                p(u'<table><tr><td width="34%" valign="top">')
                template_show_features(p, features)
                p(u'</td><td width="66%" valign="top">')
                p(html.h2('Selected Features:'))
                with html.div(p, {u'id':u'features'}):
                    pass
                p(u'</td></tr></table>')
                '''
                p(html.br())
                p(u'<table><tr><td width="100%" valign="top">')
                template_equation(p, normalized_equation, features)
                p(u'</td></tr></table>')
                '''
            with html.td_block(p, {u'width':u'34%', u'valign':u'top'}):
                with html.div(p, {u'id':u'rankings'}):
                    template_rankings(p, items, rankings)
                    template_equation(p, normalized_equation, features)
    p(template_upload_form(short_code))

def template_rankings(p, items, rankings):
    with html.table(p):
        with html.tr(p):
            with html.td_block(p, {u'valign':u'top'}):
                p(html.h2('Rankings:'))
            with html.td_block(p, {u'valign':u'top'}):
                p(u'&nbsp;')
                p(u'<button id="rerank">Re-rank</button>')
            with html.td_block(p, {u'valign':u'top'}):
                p(u'<img src="http://www.labmeeting.com/images/upload/spinner.gif" style="display:none;" id="loading" />')
    r = ['%s (%s)' % (html.b(items[i]), html.span_smaller(score)) 
                                    for score,i in rankings]
    partial_list(p, r)

def calculate_rankings(normalized_data, equation):
    elements = sorted([(f, equation[f]) for f in equation])
    features_to_use, coefficients = zip(*elements)
    normalized_data_only_features = normalized_data[:,features_to_use]
    scores = numpy.dot(normalized_data_only_features, coefficients)
    a = (100.0 / (numpy.max(scores) - numpy.min(scores)))
    normalized_scores = a * scores
    b = -1 * numpy.min(normalized_scores)
    normalized_scores += b
    rankings = reversed(sorted([(s, i) for i,s in enumerate(normalized_scores)]))
    normalized_equation = {None:b}
    for k in equation:
        normalized_equation[k] = (equation[k] * a)
    return rankings, normalized_equation

def normalize(clean_data):
    clean_data = numpy.array(clean_data)
    items,features = clean_data.shape
    for i in xrange(features):
        column = clean_data[:,i]
        clean_data[:,i] = (column - numpy.mean(column)) / numpy.std(column)
    return clean_data

def clean_column(column):
    cleaned_column = []
    for i,cell in enumerate(column):
        try:
            float(cell)
        except ValueError:
            pass
        else:
            cleaned_column.append(float(cell))
    return cleaned_column

cleaner_funcs = {u'zero': lambda c,col: 0.0,
                 u'mean': lambda c,col: numpy.mean(clean_column(col)),
                 u'median': lambda c,col: numpy.median(clean_column(col)),
                 u'min': lambda c,col: numpy.min(clean_column(col)),
                 u'max': lambda c,col: numpy.max(clean_column(col)),
                 u'mode': lambda c,col: numpy.mode(clean_column(col)),
                }
#TODO: jperla: put in protections for exceptions


def save_filters(csv_location, short_code, filter_names):
    properties = load_properties(csv_location, short_code)
    properties[u'filters'] = filter_names
    save_properties(csv_location, short_code, properties)

def load_filter_names(csv_location, short_code):
    properties = load_properties(csv_location, short_code)
    filter_names = [c for c in properties.get(u'filters', [])]
    return filter_names

def save_cleaners(csv_location, short_code, cleaners):
    properties = load_properties(csv_location, short_code)
    properties[u'cleaners'] = cleaners
    save_properties(csv_location, short_code, properties)

def load_cleaners(csv_location, short_code):
    cleaners_names = load_cleaners_names(csv_location, short_code)
    cleaners = [cleaner_funcs[c] for c in cleaners_names]
    return cleaners

def load_cleaners_names(csv_location, short_code):
    properties = load_properties(csv_location, short_code)
    cleaners_names = [c for c in properties.get(u'cleaners', [])]
    return cleaners_names

def save_properties(csv_location, short_code, properties):
    assert(short_code_valid(short_code))
    data_path = os.path.join(csv_location, '%s.json' % short_code)
    with open(data_path, 'w') as f:
        f.write(simplejson.dumps(properties))

def load_properties(csv_location, short_code):
    assert(short_code_valid(short_code))
    data_path = os.path.join(csv_location, '%s.json' % short_code)
    if not os.path.exists(data_path):
        save_properties(csv_location, short_code, {})
    with open(data_path, 'r') as f:
        properties = simplejson.loads(f.read())
    return properties
    
    

def apply_filters(x, filter_names):
    for f in filter_names:
        x = filter_funcs[f](x)
    return x

def clean_raw_data(raw_data, cleaners, filter_names):
    assert(len(cleaners) == len(raw_data[0]))
    columns = zip(*raw_data)
    clean_data = []
    for row in raw_data:
        clean_row = []
        for i,cell in enumerate(row):
            try:
                float(cell)
            except ValueError:
                #TODO: jperla: add more than just 0.0 treatment
                value = cleaners[i](cell, columns[i])
                new_value = apply_filters(value, filter_names[i])
                f = ChangedFloat(new_value)
                f.set_original(cell)
                new_float = f
            else:
                new_float = apply_filters(float(cell), filter_names[i])
            finally:
                clean_row.append(new_float)
        clean_data.append(clean_row)
    return clean_data




def template_equation(p, equation, features):
    elements = reversed(sorted([(equation[c], c) for c in equation]))
    p(html.h2(u'Equation:'))
    with html.p_block(p, {u'style':
                          u'font-family:sans;font-size:14pt;font-weight:bold;'}):
        p(u'= ' + u' + '.join([u'%s×[%s]<br />' % (unicode(weight), 
                                             html.span_smaller(features[column]))
                                                for weight,column in elements
                                                    if column is not None]))
        p(u' + %s' % equation[None])
    
def template_show_features(p, features):
    p(html.h2(u'All features:'))
    draggable_features(p, zip(range(len(features)), features), u'all_features')

def draggable_features(p, features, id):
    with html.div(p, {u'id':id}):
        for i,f in features:
            with html.div(p, {u'id':u'feature_%s' % i}):
                p(f)

def partial_list(p, things):
    with html.ol(p):
        for t in things:
            p(html.li(t))

class ChangedFloat(float):
    def set_original(self, original):
        self.original = original

def template_clean_data(p, clean_data, features, items, cleaners_names, filter_names):
    p(html.h2(u'Clean data:'))
    with html.div(p, {u'id':u'clean_data', 
                      u'style':u'height:23em;overflow:scroll;'}):
        with html.table(p):
            with html.tr(p):
                p(html.td('&nbsp;'))
                for i,f in enumerate(features):
                    with html.td_block(p):
                        p(html.b(u'Missing:'))
                        p(html.br())
                        p(u'<select class="cleaners">')
                        for name in cleaner_funcs:
                            p(u'<option')
                            if name == cleaners_names[i]:
                                p(u' SELECTED="SELECTED"')
                            p(u' value="%s"' % name)
                            p(u'>')
                            p(name)
                            p(u'</option>')
                        p(u'</select>')

                        p(html.br())
                        p(html.br())
                        p(html.b(u'Filters:'))
                        p(html.br())
                        with html.div(p, {u'class':u'filters'}):
                            for f in filter_funcs:
                                p(u'<input type="checkbox"')
                                if f in filter_names[i]:
                                    p(u' checked="checked"')
                                p(u' name="%s"' % f)
                                p(u'>')
                                p(f)
                                p(u'</input>')
                                p(html.br())
            with html.tr(p):
                p(html.td(u'&nbsp;'))
                for f in features:
                    with html.td_block(p, {u'valign':u'top'}):
                        p(html.b(f))
            for i,item in enumerate(items):
                with html.tr(p):
                    p(html.td(html.b(item)))
                    for cell in clean_data[i]:
                        if isinstance(cell, ChangedFloat):
                            p(html.td(html.b(u'%.6s ' % cell) + ('<span style="font-size:smaller;color:gray;">"%s"</span>' % cell.original)))
                        else:
                            p(html.td('%.6s' % cell))

filter_funcs = {u'negate': lambda x: -1 * x,
                u'square': lambda x: x * x,
                u'cube': lambda x: x * x * x,
                u'inverse': lambda x: 1.0 / x if x != 0 else 0.0,
                u'log': lambda x: numpy.log(x) if x > 0 else 0.0,
                u'exp': lambda x: 2.718281828 ** x
               }


                    


def template_show_data(p, table):
    p(html.h2(u'Full table:'))
    with html.div(p, {'style':'height:23em;overflow:scroll;'}):
        partial_table(p, table)

def partial_table(p, table):
    with html.table(p):
        for row in table:
            with html.tr(p):
                for cell in row:
                    p(html.td(cell))

    
import string
valid_chars = set(string.digits + string.lowercase)
def short_code_valid(short_code):
    if len(short_code) > 100:
        return False
    for c in short_code:
        if c not in valid_chars:
            return False
    return True
    

@app.subapp()
@webify.urlable()
def upload(req, p):
    if req.method == u'POST':
        short_code = req.params.get('short_code')
        assert(short_code_valid(short_code))
        uploaded_file = req.POST[u'csv']
        assert(uploaded_file.type == u'text/csv')
        assert(uploaded_file.filename.endswith('.csv'))
        data = uploaded_file.file.read()
        csv_location = req.settings[u'csv_location']
        with open(os.path.join(csv_location, short_code), 'w') as f:
            f.write(data)
        save_properties(csv_location, short_code, {})
        p(u'Thank you for uploading %s.  ' % uploaded_file.filename)
        p(html.a(view_csv.url(short_code), u'You can see it here.'))
        #TODO: jperla: redirect to new file; need a 302
    else:
        short_code = hashlib.md5(str(random.random())).hexdigest()[:15]
        p(template_upload_form(short_code))

def template_upload_form(short_code):
    yield u'<form method="POST" enctype="multipart/form-data" action="%s">' % upload.url()
    yield u'Please upload a properly formatted CSV'
    yield u'<br />'
    yield u'<input type="text" name="short_code" value="%s" />' % short_code
    yield u'<input type="file" name="csv" />'
    yield u'<input type="submit" value="Upload" />'
    yield u'</form>'

    
    
    

# Middleware
from webify.middleware import install_middleware, EvalException, SettingsMiddleware

# Server
from webify.http import server
if __name__ == '__main__':
    settings = {
                'csv_location': 'csvs/',
               }

    wsgi_app = webify.wsgify(app)

    wrapped_app = install_middleware(wsgi_app, [
                                                SettingsMiddleware(settings),
                                                EvalException,
                                               ])
    print 'Loading server...'
    server.serve(wrapped_app, host='127.0.0.1', port=8085, reload=True)

