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
Implementation of relationships.

Relationships are represented as collections of links.  A link defines one
half of a relationship.  The storage of links on an object is determined by
an IRelationshipLinks adapter.  There is a default adapter registered for
all IAnnotatable objects that uses Zope 3 annotations.
"""

from persistent import Persistent
from persistent.list import PersistentList
from zope.interface import implements
import zope.event

from schoolbell.relationship.interfaces import IRelationshipLinks
from schoolbell.relationship.interfaces import IRelationshipLink
from schoolbell.relationship.interfaces import IRelationshipProperty
from schoolbell.relationship.interfaces import IBeforeRelationshipEvent
from schoolbell.relationship.interfaces import IRelationshipAddedEvent
from schoolbell.relationship.interfaces import IBeforeRemovingRelationshipEvent
from schoolbell.relationship.interfaces import IRelationshipRemovedEvent
from schoolbell.relationship.interfaces import DuplicateRelationship
from schoolbell.relationship.interfaces import NoSuchRelationship


def relate(rel_type, (a, role_of_a), (b, role_of_b), extra_info=None):
    """Establish a relationship between objects `a` and `b`."""
    for link in IRelationshipLinks(a):
        if (link.target is b and link.role == role_of_b
            and link.rel_type == rel_type):
            raise DuplicateRelationship
    zope.event.notify(BeforeRelationshipEvent(rel_type,
                                              (a, role_of_a),
                                              (b, role_of_b)))
    IRelationshipLinks(a).add(Link(role_of_a, b, role_of_b, rel_type,
                                   extra_info))
    IRelationshipLinks(b).add(Link(role_of_b, a, role_of_a, rel_type,
                                   extra_info))
    zope.event.notify(RelationshipAddedEvent(rel_type,
                                             (a, role_of_a),
                                             (b, role_of_b)))


def unrelate(rel_type, (a, role_of_a), (b, role_of_b)):
    """Break a relationship between objects `a` and `b`."""
    links_of_a = IRelationshipLinks(a)
    links_of_b = IRelationshipLinks(b)
    try:
        link_a_to_b = links_of_a.find(role_of_a, b, role_of_b, rel_type)
    except ValueError:
        raise NoSuchRelationship
    zope.event.notify(BeforeRemovingRelationshipEvent(rel_type,
                                                      (a, role_of_a),
                                                      (b, role_of_b)))
    links_of_a.remove(link_a_to_b)
    # If links_of_b.find raises a ValueError, our data structures are out of
    # sync.
    link_b_to_a = links_of_b.find(role_of_b, a, role_of_a, rel_type)
    links_of_b.remove(link_b_to_a)
    zope.event.notify(RelationshipRemovedEvent(rel_type,
                                               (a, role_of_a),
                                               (b, role_of_b)))


def unrelateAll(obj):
    """Break all relationships of `obj`.

    Note that this operation is not atomic: if an event subscriber catches
    a BeforeRemovingRelationshipEvent and vetoes the operation, some
    relationships may have been removed, while others may still be there.
    """
    links_of_a = IRelationshipLinks(obj)
    relationships = [(link.rel_type, (obj, link.my_role),
                                     (link.target, link.role))
                     for link in links_of_a]
    for args in relationships:
        try:
            unrelate(*args)
        except NoSuchRelationship:
            pass # it was a loop, so we tried to delete it twice
    return


class RelationshipEvent(object):
    """Base class for relationship events.

        >>> event = RelationshipEvent('Membership',
        ...                           ('a', 'Member'), ('b', 'Group'))
        >>> event['Member']
        'a'
        >>> event['Group']
        'b'
        >>> event['Bogus']
        Traceback (most recent call last):
          ...
        KeyError: 'Bogus'

    """

    def __init__(self, rel_type, (a, role_of_a), (b, role_of_b)):
        self.rel_type = rel_type
        self.participant1 = a
        self.role1 = role_of_a
        self.participant2 = b
        self.role2 = role_of_b

    def __getitem__(self, role):
        """Return the participant with a given role."""
        if role == self.role1:
            return self.participant1
        if role == self.role2:
            return self.participant2
        raise KeyError(role)


class BeforeRelationshipEvent(RelationshipEvent):
    """A relationship is about to be established.

        >>> from zope.interface.verify import verifyObject
        >>> event = BeforeRelationshipEvent('example:Membership',
        ...                                 ('a', 'example:Member'),
        ...                                 ('letters', 'example:Group'))
        >>> verifyObject(IBeforeRelationshipEvent, event)
        True

    """

    implements(IBeforeRelationshipEvent)


class RelationshipAddedEvent(RelationshipEvent):
    """A relationship has been established.

        >>> from zope.interface.verify import verifyObject
        >>> event = RelationshipAddedEvent('example:Membership',
        ...                                ('a', 'example:Member'),
        ...                                ('letters', 'example:Group'))
        >>> verifyObject(IRelationshipAddedEvent, event)
        True

    """

    implements(IRelationshipAddedEvent)


class BeforeRemovingRelationshipEvent(RelationshipEvent):
    """A relationship is about to be broken.

        >>> from zope.interface.verify import verifyObject
        >>> event = BeforeRemovingRelationshipEvent('example:Membership',
        ...                 ('a', 'example:Member'),
        ...                 ('letters', 'example:Group'))
        >>> verifyObject(IBeforeRemovingRelationshipEvent, event)
        True

    """

    implements(IBeforeRemovingRelationshipEvent)


class RelationshipRemovedEvent(RelationshipEvent):
    """A relationship has been broken.

        >>> from zope.interface.verify import verifyObject
        >>> event = RelationshipRemovedEvent('example:Membership',
        ...                                  ('a', 'example:Member'),
        ...                                  ('letters', 'example:Group'))
        >>> verifyObject(IRelationshipRemovedEvent, event)
        True

    """

    implements(IRelationshipRemovedEvent)


def getRelatedObjects(obj, role, rel_type=None):
    """Return all objects related to `obj` with a given role."""
    if rel_type is None:
        return [link.target for link in IRelationshipLinks(obj)
                if link.role == role]
    else:
        return [link.target for link in IRelationshipLinks(obj)
                if link.role == role and link.rel_type == rel_type]


class RelationshipSchema(object):
    """Relationship schema.

    Boring doctest setup:

        >>> from schoolbell.relationship.tests import setUp, tearDown
        >>> from schoolbell.relationship.tests import SomeObject
        >>> setUp()
        >>> a = SomeObject('a')
        >>> b = SomeObject('b')

    Relationship schemas are syntactic sugar.  If you define a relationship
    schema like this:

        >>> URIMembership = 'example:Membership'
        >>> URIMember = 'example:Member'
        >>> URIGroup = 'example:Group'
        >>> Membership = RelationshipSchema(URIMembership,
        ...                     member=URIMember, group=URIGroup)

    Then you can create and break relationships by writing

        >>> Membership(member=a, group=b)
        >>> Membership.unlink(member=a, group=b)

    instead of having to explicitly say

        >>> relate(URIMembership, (a, URIMember), (b, URIGroup))
        >>> unrelate(URIMembership, (a, URIMember), (b, URIGroup))

    That's it.

        >>> tearDown()

    """

    def __init__(self, rel_type, **roles):
        if len(roles) != 2:
            raise TypeError("A relationship must have exactly two ends.")
        self.rel_type = rel_type
        self.roles = roles

    def __call__(self, **parties):
        """Establish a relationship."""
        self._doit(relate, **parties)

    def unlink(self, **parties):
        """Break a relationship."""
        self._doit(unrelate, **parties)

    def _doit(self, fn, **parties):
        """Extract and validate parties from keyword arguments and call fn."""
        (name_of_a, role_of_a), (name_of_b, role_of_b) = self.roles.items()
        try:
            a = parties.pop(name_of_a)
        except KeyError:
            raise TypeError('Missing a %r keyword argument.' % name_of_a)
        try:
            b = parties.pop(name_of_b)
        except KeyError:
            raise TypeError('Missing a %r keyword argument.' % name_of_b)
        if parties:
            raise TypeError("Too many keyword arguments.")
        fn(self.rel_type, (a, role_of_a), (b, role_of_b))


class RelationshipProperty(object):
    """Relationship property.

    Instead of calling global functions and passing URIs around you can define
    a property on an object and use it to create and query relationships:

        >>> class SomeClass(object): # must be a new-style class
        ...     friends = RelationshipProperty('example:Friendship',
        ...                                    'example:Friend',
        ...                                    'example:Friend')

    The property is introspectable, although that's not very useful

        >>> SomeClass.friends.rel_type
        'example:Friendship'

        >>> SomeClass.friends.my_role
        'example:Friend'

        >>> SomeClass.friends.other_role
        'example:Friend'

    IRelationshipProperty defines things you can do with a relationship
    property.

        >>> from zope.interface.verify import verifyObject
        >>> someinstance = SomeClass()
        >>> verifyObject(IRelationshipProperty, someinstance.friends)
        True

    """

    def __init__(self, rel_type, my_role, other_role):
        self.rel_type = rel_type
        self.my_role = my_role
        self.other_role = other_role

    def __get__(self, instance, owner):
        """Bind the property to an instance."""
        if instance is None:
            return self
        else:
            return BoundRelationshipProperty(instance, self.rel_type,
                                             self.my_role, self.other_role)


class BoundRelationshipProperty(object):
    """Relationship property bound to an object."""

    implements(IRelationshipProperty)

    def __init__(self, this, rel_type, my_role, other_role):
        self.this = this
        self.rel_type = rel_type
        self.my_role = my_role
        self.other_role = other_role

    def __nonzero__(self):
        try:
            iter(self).next()
        except StopIteration:
            return False
        else:
            return True

    def __len__(self):
        return len(list(self))

    def __iter__(self):
        for link in IRelationshipLinks(self.this):
            if link.role == self.other_role and link.rel_type == self.rel_type:
                yield link.target

    def add(self, other, extra_info=None):
        """Establish a relationship between `self.this` and `other`."""
        relate(self.rel_type, (self.this, self.my_role),
                              (other, self.other_role), extra_info)

    def remove(self, other):
        """Unlink a relationship between `self.this` and `other`."""
        unrelate(self.rel_type, (self.this, self.my_role),
                                (other, self.other_role))


class Link(Persistent):
    """One half of a relationship.

    A link is a simple class that holds information about one side of the
    relationship:

        >>> target = object()
        >>> my_role = 'example:Group'
        >>> role = 'example:Member'
        >>> rel_type = 'example:Membership'
        >>> link = Link(my_role, target, role, rel_type)
        >>> link.target is target
        True
        >>> link.my_role
        'example:Group'
        >>> link.role
        'example:Member'
        >>> link.rel_type
        'example:Membership'

    The attributes are documented in IRelationshipLink

        >>> from zope.interface.verify import verifyObject
        >>> verifyObject(IRelationshipLink, link)
        True

    """

    implements(IRelationshipLink)

    def __init__(self, my_role, target, role, rel_type, extra_info=None):
        self.my_role = my_role
        self.target = target
        self.role = role
        self.rel_type = rel_type
        self.extra_info = extra_info


class LinkSet(Persistent):
    """Set of links.

    This class is used internally to represent relationships.  Initially it
    is empty

        >>> linkset = LinkSet()
        >>> list(linkset)
        []

    You can add new links to it

        >>> link1 = Link('example:Group', object(), 'example:Member',
        ...              'example:Membership')
        >>> link2 = Link('example:Friend', object(), 'example:Friend',
        ...              'example:Friendship')
        >>> linkset.add(link1)
        >>> linkset.add(link2)
        >>> from sets import Set
        >>> Set(linkset) == Set([link1, link2]) # order is not preserved
        True

    You can look for links for a specific relationship

        >>> linkset.find('example:Group', link1.target, 'example:Member',
        ...              'example:Membership') is link1
        True

    If find fails, it raises ValueError, just like list.index.

        >>> linkset.find('example:Member', link1.target, 'example:Group',
        ...              'example:Membership')      # doctest: +ELLIPSIS
        Traceback (most recent call last):
          ...
        ValueError: ...

    You can remove links

        >>> linkset.remove(link2)
        >>> Set(linkset) == Set([link1])
        True

    If you try to remove a link that is not in the set, you will get a
    ValueError.

        >>> linkset.remove(link2)                   # doctest: +ELLIPSIS
        Traceback (most recent call last):
          ...
        ValueError: ...

    You can remove all links

        >>> linkset.clear()
        >>> Set(linkset) == Set([])
        True

    It is documented in IRelationshipLinks

        >>> from zope.interface.verify import verifyObject
        >>> verifyObject(IRelationshipLinks, linkset)
        True

    """

    implements(IRelationshipLinks)

    def __init__(self):
        self._links = PersistentList()

    def add(self, link):
        self._links.append(link)

    def remove(self, link):
        self._links.remove(link)

    def clear(self):
        del self._links[:]

    def __iter__(self):
        return iter(self._links)

    def find(self, my_role, target, role, rel_type):
        for link in self:
            if (link.rel_type == rel_type and link.target is target
                and link.my_role == my_role and link.role == role):
                return link
        raise ValueError(my_role, target, role, rel_type)
