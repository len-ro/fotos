import sqlite3, os

class Db:
    def __init__(self, config) -> None:
        self.config = config
        self.db_file = self.config["dbFile"] #"album.db"
        if not os.path.exists(self.db_file):
            self._conn = sqlite3.connect(self.db_file, detect_types=sqlite3.PARSE_DECLTYPES)
            #with current_app.open_resource("schema.sql") as f:
            with open("album.sql") as f:
                self._conn.executescript(f.read())
            self._conn.close()

    def create_album(self, album, force, parent_id = None):
        try:
            conn = sqlite3.connect(self.db_file, detect_types=sqlite3.PARSE_DECLTYPES)
            cursor = conn.cursor()
            self._create_album(cursor, album, force, parent_id)
        finally:
            conn.commit()
            cursor.close()
            conn.close()

    def _create_album(self, cursor, album, force, parent_id):
        if force:
            cursor.execute("delete from album where name = :name and path = :path and base_path = :base_path", album)
        album['tags'] = ','.join(album['tags'])
        album['parent_id'] = parent_id
        cursor.execute("insert into album(name, path, base_path, tags, parent_id) values (:name, :path, :base_path, :tags, :parent_id)", album)
        album_id = cursor.lastrowid
        for photo in album['photos']:
            photo['album_id'] = album_id
            photo['tags'] = ','.join(photo['tags'] or [])
            cursor.execute("insert into photo(album_id, file, width, height, thumb_width, thumb_height, caption, tags, rating, favorite, date_time) values "
            + "(:album_id, :file, :width, :height, :thumb_width, :thumb_height, :caption, :tags, :rating, :favorite, :date_time)", photo)
        
        for folder in album['folders']:
            self._create_album(cursor, folder, force, album_id)
        return album_id

    def _restrict_sql(self, tables, security_tags = []):
        restrict_tags = self.config['restrictTags'].copy()
        for stag in security_tags:
            if stag in restrict_tags:
                restrict_tags.remove(stag)

        restrict_sql = " "
        for table in tables:
            for rtag in restrict_tags:
                restrict_sql = restrict_sql + "and " + table + ".tags not like '%" + rtag + "%' "
        #print(restrict_tags, " -> ", restrict_sql)
        return restrict_sql


    def search_photo(self, album, photo, security_tags = []):
        """
        returns a single photo
        /<album>/<photo> or /<album>/thumbs/<photo> ->
        """
        try:
            conn = sqlite3.connect(self.db_file, detect_types=sqlite3.PARSE_DECLTYPES)
            cursor = conn.cursor()

            
            if album:
                cursor.execute("select album.base_path, album.path, photo.file from photo, album " 
                + "where photo.file = :file and album.name = :album" + self._restrict_sql(['photo'], security_tags), 
                {'file': photo, 'album': album})
                p = cursor.fetchone()
                if p == None: #error
                    return None
                else:
                    return p
        finally:
            conn.commit()
            cursor.close()
            conn.close()

    def search_photos(self, album = None, security_tags = [], tags = None):
        """
        returns a list of matching albums and photos
        /<album> -> 
        """
        try:
            conn = sqlite3.connect(self.db_file, detect_types=sqlite3.PARSE_DECLTYPES)
            cursor = conn.cursor()


            if album:
                cursor.execute("select * from album where (name like :name or alias like :name)" + self._restrict_sql(['album'], security_tags), {'name': '%' + album + '%'})
                albums = cursor.fetchall()
                if len(albums) == 0:
                    return None
                elif len(albums) == 1:
                    #return photos
                    album = self.rows2map(albums, cursor)[0]
                    album_id = album['id']
                    cursor.execute("select * from album where parent_id = :album_id", {'album_id': album_id})
                    result = {'album': album, 'folders': self.rows2map(cursor.fetchall(), cursor)}
                    cursor.execute("select * from photo where album_id = :album_id and (rating >= 1 or favorite == 1) " + self._restrict_sql(['photo'], security_tags) + " order by file", {'album_id': album_id})
                    result['photos'] = self.rows2map(cursor.fetchall(), cursor)
                    return result
                else:
                    return {'album': {'name': 'Search results'}, 'folders': self.rows2map(albums, cursor), 'photos': []}
        finally:
            conn.commit()
            cursor.close()
            conn.close()
        

    def rows2map(self, rows, cursor):
        names = [description[0] for description in cursor.description]
        result = []
        for row in rows:
           result.append(dict(zip(names, row))) 
        return result


    def get_user(self, id):
        """
        returns an user(id, tags)
        """
        try:
            conn = sqlite3.connect(self.db_file, detect_types=sqlite3.PARSE_DECLTYPES)
            cursor = conn.cursor()
            cursor.execute("select * from user where id = :id", {'id': id})
            p = cursor.fetchone()
            if p == None: #error
                return None
            else:
                return p
        finally:
            conn.commit()
            cursor.close()
            conn.close()