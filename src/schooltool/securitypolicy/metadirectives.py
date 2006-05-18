#
# SchoolTool - common information systems platform for school administration
# Copyright (c) 2006 Shuttleworth Foundation
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
SchoolTool security policy metadirectives.

$Id$

"""

from zope.interface import Interface
from zope.configuration.fields import Tokens, GlobalObject, PythonIdentifier
from zope.security.zcml import Permission


class ICrowdDirective(Interface):

    name = PythonIdentifier(
        title=u"Name",
        description=u"Identifier of the crowd")

    factory = GlobalObject(
        title=u"Factory",
        description=u"The factory for the crowd")


class IAllowDirective(Interface):

    interface = GlobalObject(
        title=u"Interface",
        required=False,
        description=u"An interface of the object")

    crowds = Tokens(
        title=u"Crowds",
        value_type=PythonIdentifier(title=u"Crowd"),
        required=True)

    permission = Permission(
        title=u"Permission",
        required=True)
