#!/usr/bin/env python
#
# Copyright (c) 2013 Groundworks Technologies
#
# This code is part PyBFD module (libbfd & libopcodes extension module)
#

import os
import sys
import platform

from traceback import print_exc
from distutils.core import setup, Extension
from distutils.ccompiler import new_compiler
from distutils.command.build_ext import build_ext

__author__      = "Groundworks Technologies OSS Team"
__contact__     = "oss@groundworkstech.com"
__description__ = "A Python interface to the GNU Binary File Descriptor (BFD) library."
__long_description__ = """
It's a complete (or at least tries to be) wrapper around the low level
functionality provided by GNU Binutils libopcodes and libbfd.
This allows the user to manipulate all the supported architectures and file
formats that Binutils tools does.
"""
__company__     = "Groundworks Technologies"
__year__        = "2013"
__version__     = "0.1.1"


MODULE_NAME = "pybfd"
PACKAGE_DIR = "pybfd"

final_supported_archs = list()
debug = False

# binutils / nm
NM = os.environ.get('NM', 'nm')
# libbfd / bfd.h
LIBBFD_INCLUDE_DIR = os.environ.get('LIBBFD_INCLUDE_DIR', '/usr/include')
LIBBFD_LIBRARY = os.environ.get('LIBBFD_LIBRARY', '/usr/lib/libbfd.so')
# libopcodes / dis-asm.h
LIBOPCODES_INCLUDE_DIR = os.environ.get('LIBOPCODES_INCLUDE_DIR', '/usr/include')
LIBOPCODES_LIBRARY = os.environ.get('LIBOPCODES_LIBRARY', '/usr/lib/libopcodes.so')
# libiberty / libiberty.a (only for static linking and on Darwin)
LIBIBERTY_LIBRARY = os.environ.get('LIBIBERTY_LIBRARY', '/usr/lib/libiberty.a')


class CustomBuildExtension( build_ext ):
    def __init__(self, *args, **kargs):
        self.libs = [LIBBFD_LIBRARY, LIBOPCODES_LIBRARY]
        self.static_libs = [lib for lib in self.libs if lib.endswith('.a')]
        self.shared_libs = [lib for lib in self.libs if not lib.endswith('.a')]
        self._include_dirs = [LIBBFD_INCLUDE_DIR, LIBOPCODES_INCLUDE_DIR]
        build_ext.__init__(self, *args, **kargs)

    def prepare_libs_for_cc(self, lib):
        c = self.compiler.compiler_type
        if c == "unix":
            name, ext = os.path.splitext(lib)
            if name.startswith("lib"):
                return lib[3:-len(ext)]
        raise Exception("unable to prepare libraries for %s" % c )

    def generate_source_files( self ):
        """
        Genertate source files to be used during the compile process of the
        extension module.
        This is better than just hardcoding the values on python files because
        header definitions might change along differente Binutils versions and
        we'll be able to catch the changes and keep the correct values.

        """
        from pybfd.gen_supported_disasm import get_supported_architectures, \
                                               get_supported_machines, \
                                               generate_supported_architectures_source, \
                                               generate_supported_disassembler_header, \
                                               gen_supported_archs

        #
        # Step 1 . Get the path to libopcodes and nm utility for further
        # usage.
        #
        libs_dirs = [os.path.dirname(lib) for lib in self.libs]

        print "[+] Detecting libbfd/libopcodes compiled architectures"

        #
        # Step 2 .
        #
        # Prepare the libs to be used as option of the compiler.

        path_to_bfd_header = os.path.join(LIBBFD_INCLUDE_DIR, "bfd.h")
        supported_machines = get_supported_machines(path_to_bfd_header)

        supported_archs = get_supported_architectures(
            NM,
            LIBOPCODES_LIBRARY,
            supported_machines,
            not LIBOPCODES_LIBRARY.endswith('.a'))

        source_bfd_archs_c = generate_supported_architectures_source(supported_archs, supported_machines)
        print "[+] Generating .C files..."
        gen_file = os.path.join(PACKAGE_DIR, "gen_bfd_archs.c")
        with open(gen_file, "w+") as fd:
            fd.write(source_bfd_archs_c)
        print "[+]   %s" % gen_file

        link_to_libs = [self.prepare_libs_for_cc(os.path.basename(lib)) for lib in self.shared_libs]

        c_compiler = new_compiler()
        objects = c_compiler.compile(
            [os.path.join(PACKAGE_DIR, "gen_bfd_archs.c"), ],
            include_dirs = self._include_dirs,
            )
        program = c_compiler.link_executable(
            objects,
            libraries = link_to_libs,
            library_dirs = libs_dirs,
            output_progname = "gen_bfd_archs",
            output_dir = PACKAGE_DIR
        )
        gen_tool = os.path.join(PACKAGE_DIR, "gen_bfd_archs")
        gen_file = os.path.join(self.build_lib, PACKAGE_DIR, "bfd_archs.py")
        cmd = "%s > %s" % (
                    gen_tool,
                    gen_file  )

        print "[+] Generating .py files..."
        # generate C dependent definitions
        os.system( cmd )
        # generate python specific data
        with open(gen_file, "a") as f:
            f.write( gen_supported_archs(supported_archs) )

        # Remove unused files.
        for obj in objects:
            os.unlink(obj)
        os.unlink(gen_tool)

        print "[+]   %s" % gen_file

        #
        # Step 3 . Generate header file to be used by the PyBFD extension
        #           modules bfd.c and opcodes.c.
        #
        gen_source = generate_supported_disassembler_header(supported_archs)

        if len(supported_archs) == 0:
            raise Exception("Unable to determine libopcodes' supported " \
                "platforms from '%s'" % LIBOPCODES_LIBRARY)

        print "[+] Generating .h files..."
        gen_file = os.path.join(PACKAGE_DIR, "supported_disasm.h")
        with open(gen_file, "w+") as fd:
            fd.write(gen_source)
        print "[+]   %s" % gen_file

        return supported_archs

    def _darwin_current_arch(self):
        """Add Mac OS X support."""
        if sys.platform == "darwin":
            if sys.maxsize > 2 ** 32: # 64bits.
                return platform.mac_ver()[2] # Both Darwin and Python are 64bits.
            else: # Python 32 bits
                return platform.processor()

    def build_extensions(self):
        """Compile the python extension module for further installation."""
        global final_supported_archs

        ext_extra_objects = []
        ext_libs = []
        ext_libs_dir = []
        ext_includes = []

        print "[+] Using binutils headers at:"
        for incdir in self._include_dirs:
            print "[+]   %s" % incdir

        # we'll use this include path for building.
        ext_includes += self._include_dirs

        print "[+] Using binutils libraries at:"
        for lib in self.libs:
            print "[+]   %s" % lib
        #
        # check for libopcodes / libbfd
        #
        libnames = [os.path.basename(lib) for lib in self.libs]
        libraries_paths = [os.path.dirname(lib) for lib in self.libs]
        libraries_paths = list(set(libraries_paths))  # removing duplicates
        if not all( [lib.startswith("libopcodes") or lib.startswith("libbfd") for lib in libnames] ):
            raise Exception("missing expected library (libopcodes / libbfd) in %s." % "\n".join(libraries_paths))

        ext_libs_dir += libraries_paths

        # use libs as extra objects...
        ext_extra_objects.extend( self.static_libs )
        ext_libs = [self.prepare_libs_for_cc(os.path.basename(lib)) for lib in self.shared_libs]

        # add dependecy to libiberty
        if self.static_libs or sys.platform == "darwin": # in OSX we always needs a static lib-iverty.

            if not os.path.isfile(LIBIBERTY_LIBRARY):
                raise Exception("missing expected library (libiberty) in %s." % LIBIBERTY_LIBRARY)
            ext_extra_objects.append(LIBIBERTY_LIBRARY)

        # generate .py / .h files that depends of libopcodes / libbfd currently selected
        final_supported_archs = self.generate_source_files()

        # final hacks for OSX
        if sys.platform == "darwin":
            # fix arch value.
            os.environ["ARCHFLAGS"] = "-arch %s" % self._darwin_current_arch()
            # In OSX we've to link against libintl.
            ext_libs.append("intl")

            # TODO: we have to improve the detection of gettext/libintl in OSX.. this is a quick fix.
            dirs = [
                "/usr/local/opt/gettext/lib", # homebrew
                "/opt/local/lib" # macports
            ]
            for d in dirs:
                if os.path.exists(d):
                    ext_libs_dir.append(d)

        # fix extensions.
        for extension in self.extensions:
            extension.include_dirs.extend( ext_includes )
            extension.extra_objects.extend( ext_extra_objects )
            extension.libraries.extend( ext_libs )
            extension.library_dirs.extend( ext_libs_dir )

        return build_ext.build_extensions(self)


def main():
    try:
        #
        # Create a setup for the current package in order to allow the user to
        # create different packages (build, source, etc.).
        #
        setup(
            name = MODULE_NAME,
            version = __version__,
            packages = [PACKAGE_DIR],
            description = __description__,
            long_description = __long_description__,
            url = "https://github.com/Groundworkstech/pybfd",
            ext_modules = [
                # These extensions will be augmented using runtime information
                # in CustomBuildExtension
                Extension(
                    name = "pybfd._bfd",
                    sources = ["pybfd/bfd.c"],
                ),
                Extension(
                    name = "pybfd._opcodes",
                    sources = ["pybfd/opcodes.c"],
               )
            ],
            author = __author__,
            author_email = __contact__,
            license = "GPLv2",
            cmdclass = {
                "build_ext": CustomBuildExtension
            },
            classifiers = [
                "Development Status :: 4 - Beta",
                "Intended Audience :: Developers",
                "Intended Audience :: Science/Research",
                "Intended Audience :: Other Audience",
                "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
                "Operating System :: MacOS",
                "Operating System :: POSIX",
                "Programming Language :: C",
                "Programming Language :: Assembly",
                "Programming Language :: Python :: 2 :: Only",
                "Topic :: Security",
                "Topic :: Software Development :: Disassemblers",
                "Topic :: Software Development :: Compilers",
                "Topic :: Software Development :: Debuggers",
                "Topic :: Software Development :: Embedded Systems",
                "Topic :: Software Development :: Libraries",
                "Topic :: Utilities"
            ]
            )

        global final_supported_archs
        if final_supported_archs:
           print "\n[+] %s %s / Supported architectures:" % (MODULE_NAME, __version__)
           for arch, _, _, comment in final_supported_archs:
               print "\t%-20s : %s" % (arch, comment)

    except Exception, err:
        global debug
        if debug:
            print_exc()
        print "[-] Error : %s" % err

if __name__ == "__main__":
    main()
