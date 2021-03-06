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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
"""ScoreSystem Interfaces
"""
__docformat__ = 'restructuredtext'

from decimal import Decimal, InvalidOperation

from persistent import Persistent

from zope.componentvocabulary.vocabulary import UtilityVocabulary
from zope.container.btree import BTreeContainer
from zope.container.interfaces import INameChooser
from zope.interface import implements, Interface
from zope.cachedescriptors.property import Lazy
import zope.schema
from zope.schema.vocabulary import SimpleVocabulary
import zope.security.checker

from schooltool.app.app import StartUpBase
from schooltool.app.interfaces import ISchoolToolApplication
from schooltool.requirement import interfaces
from schooltool.requirement import RequirementMessage as _


SCORESYSTEM_CONTAINER_KEY = 'schooltool.requirement.scoresystem_container'


class ScoreSystemAppStartup(StartUpBase):
    def __call__(self):
        if SCORESYSTEM_CONTAINER_KEY not in self.app:
            self.app[SCORESYSTEM_CONTAINER_KEY] = ScoreSystemContainer()
            scoresystems = self.app[SCORESYSTEM_CONTAINER_KEY]
            chooser = INameChooser(scoresystems)
            for ss in [PassFail, AmericanLetterScoreSystem,
                       ExtendedAmericanLetterScoreSystem]:
                custom_ss = CustomScoreSystem(ss.title, ss.description,
                    ss.scores, ss._bestScore, ss._minPassingScore)
                name = chooser.chooseName('', custom_ss)
                scoresystems[name] = custom_ss


class ScoreSystemContainer(BTreeContainer):
    """Container of custom score systems."""

    implements(interfaces.IScoreSystemContainer)


def getScoreSystemContainer(app):
    """Adapt app to IScoreSystemContainer, initializing if necessary"""

    return app[SCORESYSTEM_CONTAINER_KEY]


class ScoreValidationError(zope.schema.ValidationError):
    """Validation error for scores"""

    def __init__(self, score):
        super(zope.schema.ValidationError, self).__init__(score)

    def doc(self):
        return "'%s' is not a valid score." % self.args


def ScoreSystemsVocabulary(context):
    return UtilityVocabulary(context,
                             interface=interfaces.IScoreSystem)


def DiscreteScoreSystemsVocabulary(context):
    """Vocabulary of custom scoresytems"""
    terms = []
    container = interfaces.IScoreSystemContainer(ISchoolToolApplication(None))
    for name, ss in sorted(container.items()):
        if not interfaces.IDiscreteValuesScoreSystem.providedBy(ss):
            continue
        if not getattr(ss, 'hidden', False):
            token = name.encode('punycode')
            term = SimpleVocabulary.createTerm(ss, token, ss.title)
            terms.append(term)
    return SimpleVocabulary(terms)


class UNSCORED(object):
    """This object behaves like a string.

    We want this to behave as a global, meaning it's pickled by name, rather
    than value. We need to arrange that it has a suitable __reduce__.
    """

    value = None

    def __reduce__(self):
        return 'UNSCORED'

    def __repr__(self):
        return 'UNSCORED'

    def __nonzero__(self):
        return False


zope.security.checker.BasicTypes[UNSCORED] = zope.security.checker.NoProxy
UNSCORED = UNSCORED()


class AbstractScoreSystem(object):
    implements(interfaces.IScoreSystem)

    def __init__(self, title, description=None):
        self.title = title
        self.description = description

    def __repr__(self):
        return '<%s %r>' % (self.__class__.__name__, self.title)

    def isValidScore(self, score):
        """See interfaces.IScoreSystem"""
        raise NotImplementedError

    def fromUnicode(self, rawScore):
        """See interfaces.IScoreSystem"""
        raise NotImplementedError


class GlobalCommentScoreSystem(AbstractScoreSystem):
    implements(interfaces.ICommentScoreSystem)

    def __init__(self, title, description=None):
        super(GlobalCommentScoreSystem, self).__init__(title, description)
        self.__name__ = title

    def isValidScore(self, score):
        """See interfaces.IScoreSystem"""
        if score is UNSCORED:
            return True
        return isinstance(score, (str, unicode))

    def fromUnicode(self, rawScore):
        """See interfaces.IScoreSystem"""
        if not rawScore:
            return UNSCORED
        return rawScore

    def __reduce__(self):
        return 'CommentScoreSystem'


# Singleton
CommentScoreSystem = GlobalCommentScoreSystem(_('Comment'))


class AbstractValuesScoreSystem(AbstractScoreSystem):
    implements(interfaces.IValuesScoreSystem)

    def __init__(self, title, description=None):
        self.title = title
        self.description = description

    def isPassingScore(self, score):
        """See interfaces.IScoreSystem"""
        raise NotImplementedError

    def getBestScore(self):
        """See interfaces.IScoreSystem"""
        raise NotImplementedError

    def getNumericalValue(self, score):
        """See interfaces.IScoreSystem"""
        raise NotImplementedError

    def getFractionalValue(self, score):
        """See interfaces.IScoreSystem"""
        raise NotImplementedError


class DiscreteValuesScoreSystem(AbstractValuesScoreSystem):
    """Abstract Discrete Values Score System"""

    implements(interfaces.IDiscreteValuesScoreSystem)

    # See interfaces.IDiscreteValuesScoreSystem
    scores = None
    _minPassingScore = None
    _bestScore = None
    hidden = False
    _isMaxPassingScore = False

    def __init__(self, title=None, description=None,
                 scores=None, bestScore=None, minPassingScore=None,
                 isMaxPassingScore=False):
        self.title = title
        self.description = description
        self.scores = scores or []
        self._bestScore = bestScore
        self._minPassingScore = minPassingScore
        self._isMaxPassingScore = isMaxPassingScore

    def isPassingScore(self, score):
        """See interfaces.IScoreSystem"""
        if score is UNSCORED:
            return None
        if self._minPassingScore is None:
            return None
        scores = self.scoresDict
        if self._isMaxPassingScore:
            return scores[score] <= scores[self._minPassingScore]
        else:
            return scores[score] >= scores[self._minPassingScore]

    def isValidScore(self, score):
        """See interfaces.IScoreSystem"""
        if score is UNSCORED:
            return True
        for s in self.scoresDict.keys():
            if s.lower() == score.lower():
                return True
        return False

    def getBestScore(self):
        """See interfaces.IScoreSystem"""
        return self._bestScore

    def fromUnicode(self, rawScore):
        """See interfaces.IScoreSystem"""
        if not rawScore:
            return UNSCORED
        for score in self.scoresDict.keys():
            if score.lower() == rawScore.lower():
                return score
        raise ScoreValidationError(rawScore)

    def getNumericalValue(self, score):
        """See interfaces.IScoreSystem"""
        if score is UNSCORED:
            return None
        return self.scoresDict[score]

    def getFractionalValue(self, score):
        """See interfaces.IScoreSystem"""
        # get maximum and minimum score to determine the range
        maximum = self.scores[0][2]
        minimum = self.scores[-1][2]
        # normalized numerical score
        value = self.getNumericalValue(score) - minimum
        return value / (maximum - minimum)

    @Lazy
    def scoresDict(self):
        scores = [(score, value) for score, abbr, value, percent in self.scores]
        return dict(scores)

class GlobalDiscreteValuesScoreSystem(DiscreteValuesScoreSystem):

    def __init__(self, name, *args, **kwargs):
        self.__name__ = name
        super(GlobalDiscreteValuesScoreSystem, self).__init__(*args, **kwargs)

    def __reduce__(self):
        return self.__name__


PassFail = GlobalDiscreteValuesScoreSystem(
    'PassFail',
    _('Pass/Fail'), None,
    [(u'Pass', u'', Decimal(1), Decimal(60)),
     (u'Fail', u'', Decimal(0), Decimal(0))],
    u'Pass', u'Pass')

AmericanLetterScoreSystem = GlobalDiscreteValuesScoreSystem(
    'AmericanLetterScoreSystem',
    _('Letter Grade'), None,
    [('A', u'', Decimal(4), Decimal(90)),
     ('B', u'', Decimal(3), Decimal(80)),
     ('C', u'', Decimal(2), Decimal(70)),
     ('D', u'', Decimal(1), Decimal(60)),
     ('F', u'', Decimal(0), Decimal(0))],
    'A', 'D')

ExtendedAmericanLetterScoreSystem = GlobalDiscreteValuesScoreSystem(
    'ExtendedAmericanLetterScoreSystem',
    _('Extended Letter Grade'), None,
    [('A+', u'', Decimal('4.0'), Decimal(98)),
     ('A', u'', Decimal('4.0'), Decimal(93)),
     ('A-', u'', Decimal('3.7'), Decimal(90)),
     ('B+', u'', Decimal('3.3'), Decimal(88)),
     ('B', u'', Decimal('3.0'), Decimal(83)),
     ('B-', u'', Decimal('2.7'), Decimal(80)),
     ('C+', u'', Decimal('2.3'), Decimal(78)),
     ('C', u'', Decimal('2.0'), Decimal(73)),
     ('C-', u'', Decimal('1.7'), Decimal(70)),
     ('D+', u'', Decimal('1.3'), Decimal(68)),
     ('D', u'', Decimal('1.0'), Decimal(63)),
     ('D-', u'', Decimal('0.7'), Decimal(60)),
     ('F',  u'', Decimal('0.0'), Decimal(0))],
    'A+', 'D-')


class RangedValuesScoreSystem(AbstractValuesScoreSystem):
    """Abstract Ranged Values Score System"""

    implements(interfaces.IRangedValuesScoreSystem)

    # See interfaces.IRangedValuesScoreSystem
    min = None
    max = None
    hidden = False
    _minPassingScore = None

    def __init__(self, title=None, description=None,
                 min=Decimal(0), max=Decimal(100), minPassingScore=None):
        self.title = title
        self.description = description
        self.min, self.max = Decimal(min), Decimal(max)
        if minPassingScore is not None:
            minPassingScore = Decimal(minPassingScore)
        self._minPassingScore = minPassingScore

    def isPassingScore(self, score):
        """See interfaces.IScoreSystem"""
        if score is UNSCORED or self._minPassingScore is None:
            return None
        return score >= self._minPassingScore

    def isValidScore(self, score):
        """See interfaces.IScoreSystem"""
        if score is UNSCORED:
            return True
        try:
            Decimal(score)
        except TypeError:
            return False
        except InvalidOperation:
            return False
        return score >= self.min

    def getBestScore(self):
        """See interfaces.IScoreSystem"""
        return self.max

    def fromUnicode(self, rawScore):
        """See interfaces.IScoreSystem"""
        if rawScore == '':
            return UNSCORED

        try:
            score = Decimal(rawScore)
        except:
            raise ScoreValidationError(rawScore)

        if not self.isValidScore(score):
            raise ScoreValidationError(rawScore)
        return score

    def getNumericalValue(self, score):
        """See interfaces.IScoreSystem"""
        if score is UNSCORED:
            return None
        return Decimal(score)

    def getFractionalValue(self, score):
        """See interfaces.IScoreSystem"""
        # normalized numerical score
        value = self.getNumericalValue(score) - self.min
        return value / (self.max - self.min)


class PersistentRangedValuesScoreSystem(RangedValuesScoreSystem, Persistent):
    implements(interfaces.IPersistentRangedValuesScoreSystem)

    hidden = False


class GlobalRangedValuesScoreSystem(RangedValuesScoreSystem):

    def __init__(self, name, *args, **kwargs):
        self.__name__ = name
        super(GlobalRangedValuesScoreSystem, self).__init__(*args, **kwargs)

    def __reduce__(self):
        return self.__name__


PercentScoreSystem = GlobalRangedValuesScoreSystem(
    'PercentScoreSystem',
    _('Percent'), None,
    Decimal(0), Decimal(100), Decimal(60))

HundredPointsScoreSystem = GlobalRangedValuesScoreSystem(
    'HundredPointsScoreSystem',
    _('100 Points'), None,
    Decimal(0), Decimal(100), Decimal(60))


class ICustomScoreSystem(Interface):
    """Marker interface for score systems created in the widget."""


class IScoreSystemField(zope.schema.interfaces.IField):
    """A field that represents score system."""


class ScoreSystemField(zope.schema.Field):
    """Score System Field."""
    implements(IScoreSystemField)


class CustomScoreSystem(DiscreteValuesScoreSystem, Persistent):
    """ScoreSystem class for custom (user-created) score systems"""

    implements(interfaces.ICustomScoreSystem)

