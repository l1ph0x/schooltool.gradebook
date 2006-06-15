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
"""Requirement Security

$Id$
"""
from zope.component import adapts
from zope.interface import implements

from schooltool.requirement.interfaces import IRequirement
from schooltool.securitypolicy.crowds import ParentCrowd
from schooltool.app.security import LeaderCrowd
from schooltool.securitypolicy.crowds import EverybodyCrowd
from schooltool.securitypolicy.crowds import ParentCrowdTemplate
from schooltool.securitypolicy.interfaces import ICrowd
from schooltool.course.interfaces import ICourse


class IRequirementParentCrowd(ICrowd):
    """A crowd object that is used on a requirement's parent.

    This is just a marker interface.
    """


RequirementViewersCrowd = ParentCrowd(
    IRequirementParentCrowd, 'schooltool.view')


RequirementEditorsCrowd = ParentCrowd(
    IRequirementParentCrowd, 'schooltool.edit')


class RequirementRequirementEditorsCrowd(ParentCrowdTemplate):
    """People who can view subrequirements of a requirement.

    Requirement editors crowd depends on the parent object, but if
    that parent is a requirement we are retrieving permissions of it's
    parent.
    """
    adapts(IRequirement)
    implements(IRequirementParentCrowd)

    permission = 'schooltool.edit'
    interface = IRequirementParentCrowd


class RequirementRequirementViewersCrowd(ParentCrowdTemplate):
    """People who can view subrequirements of a requirement.

    Requirement viewers crowd depends on the parent object, but if
    that parent is a requirement we are retrieving permissions of it's
    parent.
    """
    adapts(IRequirement)
    implements(IRequirementParentCrowd)

    permission = 'schooltool.edit'
    interface = IRequirementParentCrowd


class CourseRequirementEditorsCrowd(LeaderCrowd):
    """People who can edit requirements of a course"""
    adapts(ICourse)
    implements(IRequirementParentCrowd)


class CourseRequirementViewersCrowd(EverybodyCrowd):
    """People who can view requirements of a course"""
    adapts(ICourse)
    implements(IRequirementParentCrowd)
