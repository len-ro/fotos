create table album (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id INTEGER,
    name TEXT NOT NULL UNIQUE,
    alias TEXT,
    path TEXT,
    base_path TEXT,
    tags TEXT,
    FOREIGN KEY (parent_id) REFERENCES album (id) 
);

create table photo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    album_id INTEGER,
    file TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    thumb_width INTEGER,
    thumb_height INTEGER,
    caption TEXT,
    tags TEXT,
    rating INTEGER,
    favorite INTEGER,
    date_time TEXT,
    FOREIGN KEY (album_id) REFERENCES album (id) 
        ON DELETE CASCADE 
        ON UPDATE NO ACTION
);

create table user (
    id TEXT PRIMARY KEY,
    tags TEXT
);s