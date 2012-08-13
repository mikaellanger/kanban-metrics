from datetime import datetime, date, timedelta
import itertools
from operator import itemgetter
import sqlite3
from functools import wraps
from math import ceil

from flask import (Flask, request, session, g, redirect, url_for,
                   abort, render_template, flash, jsonify, current_app)

# configuration
DATABASE = 'metrics.db'
DEBUG = True
SECRET_KEY = 's3ck51t'
USERNAME = 'kanban'
PASSWORD = 'metrics'
DATEFMT = '%Y-%m-%d'

app = Flask(__name__)
app.config.from_object(__name__)


def jsonp(func):
    """Wraps JSONified output for JSONP requests."""
    @wraps(func)
    def decorated_function(*args, **kwargs):
        callback = request.args.get('callback', False)
        if callback:
            data = str(func(*args, **kwargs).data)
            content = str(callback) + '(' + data + ')'
            mimetype = 'application/javascript'
            return current_app.response_class(content, mimetype=mimetype)
        else:
            return func(*args, **kwargs)
    return decorated_function


def connect_db():
    return sqlite3.connect(app.config['DATABASE'])


@app.before_request
def before_request():
    g.db = connect_db()


@app.teardown_request
def teardown_request(exception):
    g.db.close()


def avg(seq):
    return float(sum(seq) / max(len(seq), 1))


def groupby(rows, key):
    return ((k, list(groups))
            for k, groups in itertools.groupby(rows, itemgetter(key)))


def lead_time(items):
    deltas = (group[-1]['date'] - group[0]['date'] for i, group in items)
    deltas = list(max(1, delta.days) for delta in deltas)
    return ceil(avg(deltas))


def cycle_time(items):
    deltas = (
        (group[-1]['date'] -
         next(item['date'] for item in group
              if item['state'] in ('planned', 'devel')))
        for i, group in items)
    deltas = list(max(1, delta.days) for delta in deltas)
    return ceil(avg(deltas))


def since(rows, since):
    return [(i, group) for i, group in rows
            if all(item['date'] >= since for item in group)]


def calc_stats(rows):
    by_size = groupby(rows, 'size')

    total_lead_time = {}
    total_cycle_time = {}
    month_lead_time = {}
    month_cycle_time = {}

    for size, rows in by_size:
        by_item = list(groupby(rows, 'item'))
        total_lead_time[size] = lead_time(by_item)
        total_cycle_time[size] = cycle_time(by_item)

        windowed = since(by_item, (datetime.now() - timedelta(days=30)))
        month_lead_time[size] = lead_time(windowed)
        month_cycle_time[size] = cycle_time(windowed)

    total_lead_time['avg'] = ceil(avg(total_lead_time.values()))
    total_cycle_time['avg'] = ceil(avg(total_cycle_time.values()))
    month_lead_time['avg'] = ceil(avg(month_lead_time.values()))
    month_cycle_time['avg'] = ceil(avg(month_cycle_time.values()))

    return [
        ('totalLeadTime', total_lead_time),
        ('leadTime', total_cycle_time),
        ('totalCycleTime', month_lead_time),
        ('cycleTime', month_cycle_time)
    ]


def get_sizes():
    cur = g.db.execute('select id, name from sizes')
    return [dict(id=row[0], name=row[1].upper()) for row in cur.fetchall()]


@app.route('/')
def show_dash():
    cur = g.db.execute(
        """select transitions.item, item_types.name,
                  states.name, transitions.date, sizes.name
           from item_types, items, transitions, states, sizes
           where transitions.state = states.id
               and transitions.item = items.id
               and items.type = item_types.id
               and items.size = sizes.id
           order by transitions.item, transitions.date""")
    rows = [dict(item=row[0], type=row[1], state=row[2],
                 date=datetime.strptime(row[3], DATEFMT),
                 size=row[4].upper())
            for row in cur.fetchall()]

    by_type = groupby(rows, 'type')

    stats = []
    for type, rows in by_type:
        if rows:
            stats.append((type.title() + "s", calc_stats(rows)))

    sizes = [s['name'] for s in get_sizes()]
    sizes.append('Avg.')
    return render_template('dash.html', stats=stats, sizes=sizes)


@app.route('/newitem')
def new_item():
    cur = g.db.execute('select id, name from item_types')
    types = [dict(id=row[0], name=row[1].title()) for row in cur.fetchall()]
    return render_template('newitem.html', types=types, sizes=get_sizes())


@app.route('/item', methods=['GET'])
def list_items():
    cur = g.db.execute('select id, title from items order by id desc')
    items = [dict(id=row[0], title=row[1]) for row in cur.fetchall()]
    return render_template('list_items.html', items=items)


@app.route('/item', methods=['POST'])
def post_item():
    cur = g.db.execute(
        'insert into items (title, type, size) values (?, ?, ?)',
        (request.form['title'], int(request.form['type']),
         int(request.form['size'])))
    g.db.commit()
    id = cur.lastrowid
    flash('Created new item')
    return redirect(url_for(item.__name__, id=id))


@app.route('/item/<int:id>', methods=['GET'])
def item(id):
    cur = g.db.execute(
        """select items.title, item_types.name, sizes.name
           from items, item_types, sizes
           where items.id = ?
               and items.type = item_types.id
               and items.size = sizes.id""",
        (str(id),))
    row = cur.fetchone()
    item = dict(id=id, title=row[0], type=row[1].title(), size=row[2].upper())
    cur = g.db.execute(
        """select transitions.id, states.name, transitions.date
           from states, transitions
           where
               transitions.item = ?
               and transitions.state = states.id""", str(id))
    transitions = [dict(id=row[0], state=row[1].title(), date=row[2])
                   for row in cur.fetchall()]
    cur = g.db.execute('select id, name from states')
    states = [dict(id=row[0], name=row[1].title()) for row in cur.fetchall()]
    return render_template('item.html', item=item, transitions=transitions,
                           states=states)


@app.route('/item/<int:id>/t', methods=['POST'])
def add_transition(id):
    try:
        datetime.strptime(request.form['date'], DATEFMT)
    except ValueError:
        flash('Invalid date entered', 'error')
    else:
        g.db.execute(
            'insert into transitions (item, state, date) values (?, ?, ?)',
            [id, int(request.form['state']), request.form['date']])
        g.db.commit()
        flash('Added transition')
    return redirect(url_for(item.__name__, id=id))


@app.route('/item/<int:iid>/t/<int:tid>', methods=['POST'])
def del_transition(iid, tid):
    g.db.execute('delete from transitions where id = ?', (str(tid),))
    g.db.commit()
    return redirect(url_for(item.__name__, id=iid))


@app.route('/item/<int:id>', methods=['POST'])
def del_item(id):
    g.db.execute('delete from transitions where item = ?', (str(id),))
    g.db.execute('delete from items where id = ?', (str(id),))
    g.db.commit()
    return redirect(url_for(list_items.__name__))


@app.route('/api/metrics')
@jsonp
def get_metrics():
    cur = g.db.execute(
        """select transitions.item, item_types.name,
                  states.name, transitions.date, sizes.name
           from item_types, items, transitions, states, sizes
           where transitions.state = states.id
               and transitions.item = items.id
               and items.type = item_types.id
               and items.size = sizes.id
           order by transitions.item, transitions.date""")
    rows = [dict(item=row[0], type=row[1], state=row[2],
                 date=datetime.strptime(row[3], DATEFMT),
                 size=row[4].upper())
            for row in cur.fetchall()]

    by_type = groupby(rows, 'type')

    stats = {}
    for type, rows in by_type:
        if rows:
            stats[type] = dict(calc_stats(rows))

    print stats
    return jsonify(stats)


if __name__ == '__main__':
    app.run('0.0.0.0')
