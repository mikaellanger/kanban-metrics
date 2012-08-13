drop table if exists item_types;
create table item_types (
    id integer primary key autoincrement,
    name string not null
);
insert into item_types (name) values
    ('defect'),
    ('feature'),
    ('task');

drop table if exists states;
create table states (
    id integer primary key autoincrement,
    name string not null
);
insert into states (name) values
    ('backlog'),
    ('spec'),
    ('planned'),
    ('devel'),
    ('review'),
    ('release'),
    ('verify'),
    ('done');

drop table if exists sizes;
create table sizes (
    id integer primary key autoincrement,
    name string not null
);
insert into sizes(name) values
    ('s'),
    ('m'),
    ('l'),
    ('xl');

drop table if exists items;
create table items (
    id integer primary key autoincrement,
    title string not null,
    type integer not null,
    size integer not null,
    foreign key(type) references item_types(id),
    foreign key(size) references sizes(id)
);

drop table if exists transitions;
create table transitions (
    id integer primary key autoincrement,
    item integer not null,
    state integer not null,
    date text not null,
    foreign key(item) references items(id),
    foreign key(state) references states(id)
);