import sqlite3, os

class Db:
    def __init__(self, config, logger) -> None:
        self.config = config
        self.logger = logger
        self.db_file = self.config["dbFile"] #"album.db"
        if not os.path.exists(self.db_file):
            self._conn = sqlite3.connect(self.db_file, detect_types=sqlite3.PARSE_DECLTYPES)

            sqlInitFile = os.path.join(os.path.dirname(os.path.realpath(__file__)), "album.sql")
            with open(sqlInitFile) as f:
                self._conn.executescript(f.read())
            self._conn.close()

    def create_album(self, album, parent_id = None):
        try:
            conn = sqlite3.connect(self.db_file, detect_types=sqlite3.PARSE_DECLTYPES)
            cursor = conn.cursor()
            return self._create_album(cursor, album, parent_id)
        finally:
            conn.commit()
            cursor.close()
            conn.close()

    def _create_album(self, cursor, album, parent_id):
        self.logger.info(f"Importing {album['name']} {album['base_path']}/{album['path']}")
        cursor.execute("delete from album where name = :name and path = :path and base_path = :base_path", album)

        #delete rogue photos
        cursor.execute("delete from photo where album_id not in (select id from album)")
        
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
            folder['base_path'] = album['base_path']
            self._create_album(cursor, folder, album_id)
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
        #self.logger.info("%s %s -> %s" % (str(security_tags), str(restrict_tags), restrict_sql))
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
                cursor.execute("select * from album where (name = :name or alias = :name)" + self._restrict_sql(['album'], security_tags), {'name': album})
                albums = cursor.fetchall()
                if len(albums) == 0:
                    return None
                elif len(albums) == 1:
                    #return photos
                    album = self.rows2map(albums, cursor)[0]
                    album_id = album['id']
                    album_sql = album['custom_sql'] 
                    result = {'album': album}
                    #should be the first where clause: ie "photo.tags like '%ak%' and photo.rating >= 2" in:
                    #select photo.*, album.name from photo, album where photo.tags like '%ak%' and photo.rating >= 2
                    
                    sql_prefix = "select photo.*, album.name as album_name from photo, album where "
                    sql_suffix = " and photo.album_id = album.id and (photo.rating >= 1 or photo.favorite == 1) " + self._restrict_sql(['photo'], security_tags) + " order by date(photo.date_time) asc"
                    if album_sql == None:                
                        cursor.execute("select * from album where parent_id = :album_id", {'album_id': album_id})
                        result['folders'] = self.rows2map(cursor.fetchall(), cursor)
                        cursor.execute(sql_prefix + "photo.album_id = :album_id" + sql_suffix, {'album_id': album_id})
                    else:
                        result['folders'] = []
                        cursor.execute(sql_prefix + album_sql + sql_suffix)
                    result['photos'] = self.rows2map(cursor.fetchall(), cursor)
                    return result
                else:
                    return {'album': {'name': 'Search results'}, 'folders': self.rows2map(albums, cursor), 'photos': []}
        finally:
            conn.commit()
            cursor.close()
            conn.close()
        
    def list_albums(self):
        """
        returns a list of albums
        """
        try:
            conn = sqlite3.connect(self.db_file, detect_types=sqlite3.PARSE_DECLTYPES)
            cursor = conn.cursor()
            
            cursor.execute("select name, path, tags from album where parent_id is null order by name")
            p = cursor.fetchall()
            if p == None: #error
                return None
            else:
                return {'folders': self.rows2map(p, cursor), 'album': {'name': 'list'}}
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