#!/usr/bin/env python

############################################################################
#
# MODULE:       g.extension
# AUTHOR(S):   	Markus Neteler
#               Pythonized by Martin Landa
# PURPOSE:      Tool to download and install extensions from GRASS Addons SVN into 
#               local GRASS installation
# COPYRIGHT:    (C) 2009-2011 by Markus Neteler, and the GRASS Development Team
#
#               This program is free software under the GNU General
#               Public License (>=v2). Read the file COPYING that
#               comes with GRASS for details.
#
# TODO: add sudo support where needed (i.e. check first permission to write into
#       $GISBASE directory)
#############################################################################

#%module
#% label: Tool to maintain the extensions in local GRASS installation.
#% description: Downloads, installs extensions from GRASS Addons SVN repository into local GRASS installation or removes installed extensions.
#% keywords: general
#% keywords: installation
#% keywords: extensions
#%end

#%option
#% key: extension
#% type: string
#% key_desc: name
#% description: Name of extension to install/remove
#% required: no
#%end
#%option
#% key: operation
#% type: string
#% description: Operation to be performed
#% required: no
#% options: add,remove
#% answer: add
#%end
#%option
#% key: svnurl
#% type: string
#% key_desc: url
#% description: SVN Addons repository URL
#% required: yes
#% answer: https://svn.osgeo.org/grass/grass-addons/grass7
#%end
#%option
#% key: prefix
#% type: string
#% key_desc: path
#% description: Prefix where to install extension
#% answer: $GRASS_ADDON_PATH
#% required: yes
#%end

#%flag
#% key: l
#% description: List available modules in the GRASS Addons SVN repository
#% guisection: Print
#%end
#%flag
#% key: f
#% description: List available modules in the GRASS Addons SVN repository including modules description
#% guisection: Print
#%end
#%flag
#% key: g
#% description: List available modules in the GRASS Addons SVN repository (shell script style)
#% guisection: Print
#%end
#%flag
#% key: d
#% description: Don't delete downloaded source code when installing new extension
#%end
#%flag
#% key: i
#% description: Don't install new extension, just compile it
#%end

import os
import sys
import re
import atexit

import urllib

from grass.script import core as grass

# temp dir
remove_tmpdir = True
tmpdir = grass.tempfile()
grass.try_remove(tmpdir)
os.mkdir(tmpdir)

def check():
    # check if we have the svn client
    if not grass.find_program('svn', ['help']):
        grass.fatal(_('svn client required. Please install subversion first.'))
    # probably test here if we have "make" and "install" programs as well. how about gcc?

def expand_module_class_name(c):
    name = { 'd'  : 'display',
             'db' : 'database',
             'g'  : 'general',
             'i'  : 'imagery',
             'm'  : 'misc',
             'ps' : 'postscript',
             'p'  : 'paint',
             'r'  : 'raster',
             'r3' : 'raster3D',
             's'  : 'sites',
             'v'  : 'vector' }
    
    if name.has_key(c):
        return name[c]
    
    return c

def list_available_modules(svnurl, full = False, shell = False):
    grass.message(_('Fetching list of modules from GRASS-Addons SVN (be patient)...'))
    pattern = re.compile(r'(<li><a href=".+">)(.+)(</a></li>)', re.IGNORECASE)
    i = 0
    prefix = ['d', 'db', 'g', 'i', 'ps',
              'p', 'r', 'r3', 'v']
    nprefix = len(prefix)
    for d in prefix:
        if shell:
            grass.percent(i, nprefix, 1)
            i += 1
        
        modclass = expand_module_class_name(d)
        url = svnurl + '/' + modclass
        f = urllib.urlopen(url)
        if not f:
            grass.warning(_("Unable to fetch '%s'") % url)
            continue
        
        for line in f.readlines():
            # list modules
            sline = pattern.search(line)
            if sline and sline.group(2).split('.', 1)[0] == d:
                name = sline.group(2).rstrip('/')
                print_module_desc(name, url, full, shell)
    
    if shell:
        grass.percent(1, 1, 1)
    
def print_module_desc(name, url, full = False, shell = False):
    if not full and not shell:
        print name
        return
    
    if shell:
        print 'name=' + name
    
    # check main.c first
    desc = get_module_desc(url + '/' + name + '/' + name)
    if not desc:
        desc = get_module_desc(url + '/' + name + '/main.c', script = False)
    if not desc:
        if not shell:
            print name + '-'
            return
    
    if shell:
        print 'description=' + desc.get('description', '')
        print 'keywords=' + ','.join(desc.get('keywords', list()))
    else:
        print name + ' - ' + desc.get('description', '')
    
def get_module_desc(url, script = True):
    grass.debug('url=%s' % url)
    f = urllib.urlopen(url)
    if script:
        ret = get_module_script(f)
    else:
        ret = get_module_main(f)
        
    return ret

def get_module_main(f):
    if not f:
        return dict()
    
    ret = { 'keyword' : list() }
    
    pattern = re.compile(r'(module.*->)(.+)(=)(.*)', re.IGNORECASE)
    keyword = re.compile(r'(G_add_keyword\()(.+)(\);)', re.IGNORECASE)
    
    key   = ''
    value = ''
    for line in f.readlines():
        line = line.strip()
        find = pattern.search(line)
        if find:
            key = find.group(2).strip()
            line = find.group(4).strip()
        else:
            find = keyword.search(line)
            if find:
                ret['keyword'].append(find.group(2).replace('"', '').replace('_(', '').replace(')', ''))
        if key:
            value += line
            if line[-2:] == ');':
                value = value.replace('"', '').replace('_(', '').replace(');', '')
                if key == 'keywords':
                    ret[key] = map(lambda x: x.strip(), value.split(','))
                else:
                    ret[key] = value
                
                key = value = ''
    
    return ret

def get_module_script(f):
    ret = dict()
    if not f:
        return ret
    
    begin = re.compile(r'#%.*module', re.IGNORECASE)
    end   = re.compile(r'#%.*end', re.IGNORECASE)
    mline = None
    for line in f.readlines():
        if not mline:
            mline = begin.search(line)
        if mline:
            if end.search(line):
                break
            try:
                key, value = line.split(':', 1)
                key = key.replace('#%', '').strip()
                value = value.strip()
                if key == 'keywords':
                    ret[key] = map(lambda x: x.strip(), value.split(','))
                else:
                    ret[key] = value
            except ValueError:
                pass
    
    return ret

def cleanup():
    global tmpdir, remove_tmpdir
    if remove_tmpdir:
        grass.try_rmdir(tmpdir)
    else:
        grass.info(_("Path to the source code: '%s'") % tmpdir)
                        
def install_extension(svnurl, prefix, module, no_install):
    gisbase = os.getenv('GISBASE')
    if not gisbase:
        grass.fatal(_('$GISBASE not defined'))
    
    if grass.find_program(module):
        grass.warning(_("Extension '%s' already installed. Will be updated...") % module)
    
    classchar = module.split('.', 1)[0]
    moduleclass = expand_module_class_name(classchar)
    url = svnurl + '/' + moduleclass + '/' + module
        
    grass.message(_("Fetching '%s' from GRASS-Addons SVN (be patient)...") % module)
    global tmpdir
    os.chdir(tmpdir)
    if grass.verbosity() == 0:
        outdev = open(os.devnull, 'w')
    else:
        outdev = sys.stdout
    
    if grass.call(['svn', 'checkout',
                   url], stdout = outdev) != 0:
        grass.fatal(_("GRASS Addons '%s' not found in repository") % module)

    os.chdir(os.path.join(tmpdir, module))
    
    grass.message(_("Compiling '%s'...") % module)
    if grass.call(['make',
                   'MODULE_TOPDIR=%s' % gisbase.replace(' ', '\ ')],
                   stdout = outdev) != 0:
        grass.fatal(_('Compilation failed, sorry. Please check above error messages.'))
    
    if no_install:
        return
    
    grass.message(_("Installing '%s'...") % module)
    # can we write ?
    try:
        # replace with something better
        file = os.path.join(prefix, 'test')
        f = open(file, "w")
        f.close()
        os.remove(file)
        
        ret = grass.call(['make',
                          'MODULE_TOPDIR=%s' % gisbase,
                          'INST_DIR=%s' % prefix,
                          'install'],
                          stdout = outdev)
    except IOError:
        ret = grass.call(['sudo', 'make',
                          'MODULE_TOPDIR=%s' % gisbase,
                          'INST_DIR=%s' % prefix,
                          'install'],
                          stdout = outdev)
    
    if ret != 0:
        grass.warning(_('Installation failed, sorry. Please check above error messages.'))
    else:
        grass.message(_("Installation of '%s' successfully finished.") % module)

def remove_extension(prefix, module):
    # is module available?
    if not os.path.exists(os.path.join(prefix, 'bin', module)):
        grass.fatal(_("Module '%s' not found") % module)
    
    for file in [os.path.join(prefix, 'bin', module),
                 os.path.join(prefix, 'scripts', module),
                 os.path.join(prefix, 'docs', 'html', module + '.html')]:
        if os.path.isfile(file):
            os.remove(file)
                    
    grass.message(_("'%s' successfully uninstalled.") % module)

def create_dir(path):
    if os.path.isdir(path):
        return
    
    try:
        os.makedirs(path)
    except OSError, e:
        grass.fatal(_("Unable to create '%s': %s") % (path, e))
    
    grass.debug("'%s' created" % path)
    
def check_dirs():
    create_dir(os.path.join(options['prefix'], 'bin'))
    create_dir(os.path.join(options['prefix'], 'docs', 'html'))
    create_dir(os.path.join(options['prefix'], 'man', 'man1'))

def main():
    # check dependecies
    check()
    
    # list available modules
    if flags['l'] or flags['f'] or flags['g']:
        list_available_modules(options['svnurl'], full = flags['f'], shell = flags['g'])
        return 0
    else:
        if not options['extension']:
            grass.fatal(_('You need to define an extension name or use -l'))
    
    # define path
    if options['prefix'] == '$GRASS_ADDON_PATH':
        if not os.environ.has_key('GRASS_ADDON_PATH') or \
                not os.environ['GRASS_ADDON_PATH']:
            grass.warning(_("GRASS_ADDON_PATH is not defined, installing to ~/.grass7/addons/"))
            options['prefix'] = os.path.join(os.environ['HOME'], '.grass7', 'addons')
    
    # check dirs
    check_dirs()
    
    if flags['d']:
        if options['operation'] != 'add':
            grass.warning(_("Flag 'd' is relevant only to 'operation=add'. Ignoring this flag."))
        else:
            global remove_tmpdir
            remove_tmpdir = False
    
    if options['operation'] == 'add':
        install_extension(options['svnurl'], options['prefix'], options['extension'], flags['i'])
    else: # remove
        remove_extension(options['prefix'], options['extension'])
    
    return 0

if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    sys.exit(main())
