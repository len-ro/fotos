import os, shutil, datetime
import pyexiv2, datetime, json
from PIL import Image, ImageOps

class AlbumParser:
    def __init__(self, config, logger) -> None:
        self.config = config
        self.logger = logger
        self.skipDirs = [self.config["albumDir"], self.config["thumbDir"], 'js', 'css', 'default-skin', 'img']

    def import_album(self, path):
        """ imports an already created album folder """
        for basePath in self.config["paths"]:
            testPath = os.path.join(basePath, path)
            if os.path.exists(testPath):
                fullPath = os.path.join(basePath, path)

                #parsed in a different place, just load in the db
                albumDataFile = os.path.join(fullPath, self.config["albumDir"], self.config["albumDataFile"])
                if os.path.exists(albumDataFile) and os.path.isfile(albumDataFile):
                    self.logger.info("Loading %s" % albumDataFile)
                    with open(albumDataFile) as json_file:
                        album = json.load(json_file)
                        album['base_path'] = basePath
                        return album
                else:
                    raise Exception("Missing %s" % albumDataFile)
        raise Exception("Cannot find album %s in %s" % (path, self.config['paths'].join(',')))

    def parse(self, path, deleteExisting):
        for basePath in self.config["paths"]:
            testPath = os.path.join(basePath, path)
            if os.path.exists(testPath):
                #find only the first matching path
                return self.parse_album_folder(basePath, path, deleteExisting)

    def parse_album_folder(self, basePath, path, deleteExisting, parent = None):
        """ parses an album folder which might contain sub folders """
        fullPath = os.path.join(basePath, path)

        #load album tags from file
        albumDataFile = os.path.join(fullPath, self.config["albumDir"], self.config["albumDataFile"])
        album = None
        thisIsAFotosAlbum = False
        if os.path.exists(albumDataFile) and os.path.isfile(albumDataFile):
            thisIsAFotosAlbum = True
            with open(albumDataFile) as json_file:
                album = json.load(json_file)

        tags = None
        if album:
            tags = album['tags']

        album_name = os.path.basename(fullPath)
        if parent:
            album_name = f'{parent}__{album_name}'

        album = { 
            "name": album_name,
            "base_path": basePath,
            "path": path,
            "photos": [],
            "folders": [],
            "tags": tags or []
        }

        albumFolder = os.path.join(fullPath, self.config["albumDir"])
        hasAlbum = os.path.exists(albumFolder) #check if there is an album folder already
        if deleteExisting and hasAlbum and thisIsAFotosAlbum: 
            #if deleteExisting, remove existing album to regenerate but only if this is a fotos album, don't delete old album, they might contain usefull info
            shutil.rmtree(albumFolder)
            hasAlbum = False

        if not os.path.exists(albumFolder):
            os.makedirs(albumFolder)
        for f in os.listdir(fullPath):
            filePath = os.path.join(fullPath, f)
            if os.path.isdir(filePath) and f not in self.skipDirs:
                #handle subfolders
                album['folders'].append(self.parse_album_folder(basePath, os.path.join(path, f), deleteExisting, album_name))
            else:
                #handle photos
                refFile = f.upper()
                if refFile.endswith(tuple(self.config["formats"])):
                    image = self.parse_image(fullPath, f, hasAlbum)
                    album['photos'].append(image)

        #save parsed album to a file
        with open(albumDataFile, 'w') as outfile:
            json.dump(album, outfile, indent=4, default=str)

        return album

    def parse_image(self, root, file, hasAlbum):
        """
        :param bool hasAlbum: there is an album folder already, don't regenerate photos
        """
        imgPath = os.path.join(root, file)
        imgPathRelForSymlink = os.path.join("..", file) 
        albumImgPath = os.path.join(root, self.config["albumDir"], file)
        albumImgPath = albumImgPath.replace(".JPG", ".jpg")
        thumbImgPath = os.path.join(root, self.config["albumDir"], self.config["thumbDir"], file)
        thumbImgPath = thumbImgPath.replace(".JPG", ".jpg")

        #self.logger.info('Processing %s to %s and %s' % (imgPath, albumImgPath, thumbImgPath))

        if os.path.exists(albumImgPath):
            metadata = pyexiv2.metadata.ImageMetadata(albumImgPath)
        else:
            metadata = pyexiv2.metadata.ImageMetadata(imgPath)
        metadata.read()
        
        caption = self.get_exif_tag(metadata, self.config["exif"]["captionKeys"])
        if caption:
            caption = caption.value.strip()
            if len(caption) > 0:
                caption = 'data-title="%s"' % caption.value
        else:
            caption = ''

        dateTime = self.get_exif_tag(metadata, self.config["exif"]["dateKeys"])
        if dateTime:
            dateTime = dateTime.value
        else:
            dateTime = datetime.datetime.today() 

        favorite = self.get_exif_tag(metadata, self.config["exif"]["favoriteKeys"])
        if favorite:
            favorite = favorite.value
        favorite = favorite == '1'

        tags = self.get_exif_tag(metadata, self.config["exif"]["tagsKeys"])
        if tags:
            tags = tags.value

        rating = self.get_exif_tag(metadata, self.config["exif"]["ratingKeys"])
        if os.path.exists(albumImgPath):
            #the album was already generated, update rating for selected album photos to at least 1
            if rating:
                rating_value = rating.value
                if rating_value == 0:
                    rating.value = 1
                    metadata.write()
            else:
                tag_name = self.config["exif"]["ratingKeys"][0]
                metadata[tag_name] = pyexiv2.XmpTag(tag_name, 1)
                metadata.write()

        rating = self.get_exif_tag(metadata, self.config["exif"]["ratingKeys"])
        if rating:
            rating = rating.value
        else:
            rating = 0

        #self.logger.info(f"Rating {file} -> {rating}")

        thumbSize = (0, 0)
        im = Image.open(imgPath)
        imgSize = im.size
        im.close()

        if rating >= 1 or favorite:
            self.logger.info("Ensure photo and thumb for %s" % file)
            #generate the album if not already generated and if image is selected

            #clean metadata
            self.clean_exif(metadata)

            #create thumbnail
            if rating >= self.config["ratingLargeThumb"]:
                size = self.config["thumbSizeLarge"]
            else:
                size = self.config["thumbSizeSmall"]
            thumbSize = self.scale_image(imgPath, thumbImgPath, size, metadata)

            #create album image
            if not os.path.exists(albumImgPath):
                size = self.config["imageSize"]
                if imgSize[0] >= size or imgSize[1] >= size:
                    imgSize = self.scale_image(imgPath, albumImgPath, size, metadata)
                else:
                    #image is small, no resize needed, create symlink
                    if(os.path.exists(albumImgPath)):
                        os.remove(albumImgPath)
                    os.symlink(imgPathRelForSymlink, albumImgPath) #symlink must be relative otherwise will get destroyed by rsync   

        return {'date_time': dateTime, 'file': file, 'caption': caption, 
            'width': imgSize[0], 'height': imgSize[1], 
            'thumb_width': thumbSize[0], 'thumb_height': thumbSize[1],
            'thumbDir': self.config["thumbDir"], 'tags': tags, 'rating': rating, 'favorite': favorite}

    def get_exif_tag(self, metadata, keys):
        """return first tag from keys or none if nothing found"""
        all_keys = metadata.exif_keys + metadata.iptc_keys + metadata.xmp_keys
        for k in keys:
            if k in all_keys:
                return metadata[k]
        return None

    def clean_exif(self, metadata):
        """clean metadata"""
        all_keys = metadata.exif_keys + metadata.iptc_keys + metadata.xmp_keys
        keep_keys = self.config['exif']['captionKeys'] + self.config['exif']['ratingKeys'] + self.config['exif']['tagsKeys'] + self.config['exif']['dateKeys'] + self.config['exif']['keepKeys']

        for k in all_keys:
            if k not in keep_keys:
                del metadata[k]

    def scale_image(self, imgPath, scaledImgPath, size, metadata):
        dirName = os.path.dirname(scaledImgPath)
        if not os.path.exists(dirName):
            os.makedirs(dirName)

        im = Image.open(imgPath)
        #either this or keep orientation in exif "Exif.Image.Orientation"
        im = ImageOps.exif_transpose(im)

        newSize = [int(im.width * size / im.height), size]

        #im.thumbnail(size, Image.ANTIALIAS)
        im = im.resize(newSize, Image.LANCZOS)
        im.save(scaledImgPath, "JPEG")
        
        if metadata:
            newMetadata = pyexiv2.metadata.ImageMetadata(scaledImgPath)
            newMetadata.read()
            metadata.copy(newMetadata)
            newMetadata.write()

        return im.size