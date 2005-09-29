#
# SchoolTool - common information systems platform for school administration
# Copyright (c) 2005 Shuttleworth Foundation
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
"""
Functional Testing Utilities

$Id$
"""

import os
import unittest

from zope.testing import doctest
from zope.app.testing.functional import FunctionalTestSetup
from zope.app.testing.functional import FunctionalDocFileSuite

from schooltool.testing import analyze


def find_ftesting_zcml():
    """Find ftesting.zcml to be used for SchoolTool functional tests."""
    dir = os.path.abspath(os.path.dirname(__file__))
    while True:
        filename = os.path.join(dir, 'schooltool-skel', 'etc', 'ftesting.zcml')
        if os.path.exists(filename):
            return filename
        dir = os.path.dirname(dir)
        if dir == os.path.dirname(dir): # we're looping at the filesystem root
            raise RuntimeError("I can't find ftesting.zcml!")


def load_ftesting_zcml():
    """Find SchoolTool's ftesting.zcml and load it.

    Can be safely called more than once.
    """
    # Find SchoolTool's ftesting.zcml and load it.
    try:
        FunctionalTestSetup(find_ftesting_zcml())
    except NotImplementedError, e:
        # It appears that some other ftesting.zcml was already loaded, which
        # is perfectly fine -- the user might be running Zope 3 tests.
        if str(e) != 'Already configured with a different config file':
            raise


def collect_ftests(package=None, level=None):
    """Collect all functional doctest files in a given package.

    If `package` is None, looks up the call stack for the right module.

    Returns a unittest.TestSuite.
    """
    package = doctest._normalize_module(package)
    testdir = os.path.dirname(package.__file__)
    filenames = [fn for fn in os.listdir(testdir)
                 if fn.endswith('.txt') and not fn.startswith('.')]
    optionflags = (doctest.ELLIPSIS | doctest.REPORT_NDIFF |
                   doctest.NORMALIZE_WHITESPACE |
                   doctest.REPORT_ONLY_FIRST_FAILURE)
    suites = []
    for filename in filenames:
        suite = FunctionalDocFileSuite(filename, package=package,
                                       optionflags=optionflags,
                                       globs={'analyze': analyze})
        if level is not None:
            suite.level = level
        suites.append(suite)
    return unittest.TestSuite(suites)

