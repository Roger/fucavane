#!/usr/bin/env python
# -*- coding: utf-8 -*-

import threading
import fuse

# TODO: better imports
from errno import *
from stat import *

from defuse.fs import FS, BaseMetadata
from pycavane.megaupload import MegaFile

from pycavane import pycavane
import logger


pycapi = pycavane.Pycavane()

fuse.fuse_python_api = (0, 2)

fs = FS.get()

# Directory Metadata
dir_mode = S_IRUSR|S_IXUSR|S_IWUSR|S_IRGRP|S_IXGRP|S_IXOTH|S_IROTH
dir_metadata = BaseMetadata(dir_mode, True)

# File Metadata
file_mode = S_IRUSR|S_IWUSR|S_IRGRP|S_IROTH
file_metadata = BaseMetadata(file_mode, False)

# TODO: need configuration
NULLHACK = False


@fs.route('/')
class Root(object):
    @logger.log()
    def getattr(self, *args, **kwargs):
        return dir_metadata

    @logger.log()
    def readdir(self, *args, **kwargs):
        yield fuse.Direntry('shows')
        yield fuse.Direntry('movies')


@fs.route('/shows')
class ShowsDir(object):
    @logger.log()
    def getattr(self, *args, **kwargs):
        return dir_metadata

    @logger.log()
    def readdir(self, *args, **kwargs):
        for show in pycapi.get_shows():
            yield fuse.Direntry(show[1])


@fs.route('/movies')
class MoviesDir(object):
    @logger.log()
    def getattr(self, *args, **kwargs):
        return dir_metadata

    @logger.log()
    def readdir(self, *args, **kwargs):
        yield -ENOENT


@fs.route('/shows/<show>')
class Shows(object):
    @logger.log()
    def getattr(self, *args, **kwargs):
        show = kwargs['show']
        if pycapi.show_by_name(show):
            return dir_metadata
        return -ENOENT

    @logger.log()
    def readdir(self, *args, **kwargs):
        show = kwargs['show']
        for season in pycapi.seasson_by_show(show):
            yield fuse.Direntry(season[1])


@fs.route('/shows/<show>/<season>')
class Season(object):
    @logger.log()
    def getattr(self, *args, **kwargs):
        show = kwargs['show']
        season = kwargs['season']
        if [s for s in pycapi.seasson_by_show(show) if s[1] == season]:
            return dir_metadata
        return -ENOENT

    @logger.log()
    def readdir(self, *args, **kwargs):
        show = kwargs['show']
        season = kwargs['season']
        for episode in pycapi.episodes_by_season(show, season):
            name = '%02i:: %s' % (int(episode[1]), episode[2])
            yield fuse.Direntry(name + '.mp4')
            yield fuse.Direntry(name + '.srt')
            if NULLHACK:
                yield fuse.Direntry(name + '.nul')

@fs.route('/shows/<show>/<season>/<number>:: <episode>.<ext>')
class Episodes(object):
    def __init__(self):
        self.episodes = {}
        self.opening = False
        self.lock = threading.RLock()

    def get_id(self, **kwargs):
        show = kwargs['show']
        season = kwargs['season']
        episode = kwargs['episode']
        ext = kwargs['ext']

        return '/'.join((show, season, episode, ext))

    @logger.log()
    def getattr(self, *args, **kwargs):
        show = kwargs['show']
        season = kwargs['season']
        episode = kwargs['episode']
        ext = kwargs['ext']
        if ext not in ('nul', 'mp4', 'srt'):
            return -ENOENT

        exists =  [ep for ep in pycapi.episodes_by_season(show, season) \
                                                        if ep[2]==episode]
        if exists:
            return file_metadata
        return -ENOENT

    @logger.log()
    def open(self, *args, **kwargs):
        with self.lock:
            self.opening = True
            show = kwargs['show']
            season = kwargs['season']
            episode = kwargs['episode']
            ext = kwargs['ext']

            id = self.get_id(**kwargs)

            episode =  [ep for ep in pycapi.episodes_by_season(show, season) \
                                                            if ep[2]==episode]
            episode = episode[0]

            if id not in self.episodes:
                self.episodes[id] = {'episode': episode}
                if ext == 'mp4':
                    direct_link = pycapi.get_direct_links(episode,
                                                host='megaupload')[1]

                    # TODO: setup cache
                    self.episodes[id]['handle'] = MegaFile(direct_link, '/tmp/')
                    self.episodes[id]['handle'].start()
            if ext == 'mp4':
                handle = self.episodes[id].get('handle', None)
                if handle:
                    handle.open()
            self.opening = False

    @logger.log()
    def read(self, size, offset, **kwargs):
        with self.lock:
            ext = kwargs['ext']

            id = self.get_id(**kwargs)

            if ext == 'mp4':
                handle = self.episodes[id]['handle']
                return handle.read(offset, size)
            elif ext == 'srt':
                episode = self.episodes[id]['episode']
                handle = pycapi.get_subtitle(episode)
                return handle[offset:offset+size]
            elif ext == 'nul':
                return ''
            else:
                print 'WTF', ext
                return -ENOENT

    @logger.log()
    def release(self, *args, **kwargs):
        with self.lock:
            ext = kwargs['ext']

            id = self.get_id(**kwargs)
            if ext == 'mp4' and id in self.episodes:
                handle = self.episodes[id].get('handle', None)
                if handle:
                    handle.release()
