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
Report Card Views
"""

from zope.component import getUtilitiesFor
from zope.schema.vocabulary import SimpleVocabulary
from zope.container.interfaces import INameChooser
from zope.browserpage.viewpagetemplatefile import ViewPageTemplateFile
from zope.component import adapts
from zope.interface import Interface, implements
from zope.schema import Choice, Int
from zope.security.checker import canWrite
from zope.security.interfaces import Unauthorized
from zope.traversing.api import getName
from zope.traversing.browser.absoluteurl import absoluteURL
from zope.lifecycleevent.interfaces import IObjectAddedEvent

from z3c.form import form, field, button

from schooltool.app.interfaces import ISchoolToolApplication
from schooltool.gradebook import GradebookMessage as _
from schooltool.common.inlinept import InheritTemplate
from schooltool.course.interfaces import ISectionContainer, ISection
from schooltool.person.interfaces import IPerson
from schooltool.schoolyear.interfaces import ISchoolYear
from schooltool.skin import flourish
from schooltool.term.interfaces import ITerm
from schooltool.schoolyear.subscriber import ObjectEventAdapterSubscriber

from schooltool.gradebook.interfaces import (IGradebookRoot,
    IGradebookTemplates, IReportWorksheet, IReportActivity, IActivities)
from schooltool.gradebook.activity import (Worksheet, Activity, ReportWorksheet,
    ReportActivity)
from schooltool.gradebook.category import getCategories
from schooltool.gradebook.gradebook_init import ReportLayout, ReportColumn
from schooltool.gradebook.gradebook_init import OutlineActivity
from schooltool.requirement.interfaces import ICommentScoreSystem
from schooltool.requirement.interfaces import IScoreSystem
from schooltool.requirement.interfaces import IRangedValuesScoreSystem
from schooltool.requirement.scoresystem import RangedValuesScoreSystem
from schooltool.requirement.scoresystem import DiscreteScoreSystemsVocabulary


ABSENT_HEADING = _('Absent')
TARDY_HEADING = _('Tardy')
ABSENT_ABBREVIATION = _('A')
TARDY_ABBREVIATION = _('T')
ABSENT_KEY = 'absent'
TARDY_KEY = 'tardy'


def copyActivities(sourceWorksheet, destWorksheet):
    """Copy the activities from the source worksheet to the destination."""

    for key, activity in sourceWorksheet.items():
        activityCopy = Activity(activity.title, activity.category,
                                activity.scoresystem, activity.description,
                                activity.label)
        destWorksheet[key] = activityCopy


class TemplatesView(object):
    """A view for managing report sheet templates"""

    @property
    def worksheets(self):
        """Get  a list of all worksheets."""
        pos = 0
        for worksheet in self.context.values():
            pos += 1
            yield {'name': getName(worksheet),
                   'title': worksheet.title,
                   'url': absoluteURL(worksheet, self.request),
                   'pos': pos}

    def positions(self):
        return range(1, len(self.context.values())+1)

    def canModify(self):
        return canWrite(self.context, 'title')

    def update(self):
        self.person = IPerson(self.request.principal, None)
        if self.person is None:
            # XXX ignas: i had to do this to make the tests pass,
            # someone who knows what this code should do if the user
            # is unauthenticated should add the relevant code
            raise Unauthorized("You don't have the permission to do this.")

        if 'DELETE' in self.request:
            for name in self.request.get('delete', []):
                del self.context[name]

        elif 'form-submitted' in self.request:
            old_pos = 0
            for worksheet in self.context.values():
                old_pos += 1
                name = getName(worksheet)
                if 'pos.'+name not in self.request:
                    continue
                new_pos = int(self.request['pos.'+name])
                if new_pos != old_pos:
                    self.context.changePosition(name, new_pos-1)


class FlourishManageReportSheetsOverview(flourish.page.Content):

    body_template = ViewPageTemplateFile(
        'templates/f_manage_report_sheets_overview.pt')

    @property
    def templates(self):
        return IGradebookTemplates(ISchoolToolApplication(None), None)


class FlourishTemplatesView(flourish.page.Page):
    """A flourish view for managing report sheet templates"""

    def update(self):
        if 'form-submitted' in self.request:
            for template in self.context.values():
                name = 'delete.%s' % template.__name__
                if name in self.request:
                    del self.context[template.__name__]
                    return


class FlourishReportSheetsOverviewLinks(flourish.page.RefineLinksViewlet):
    """flourish report sheet templates overview add links viewlet."""


class FlourishReportSheetAddView(flourish.form.AddForm):
    """flourish view for adding a report sheet template."""

    fields = field.Fields(IReportWorksheet).select('title')
    template = InheritTemplate(flourish.page.Page.template)
    label = None
    legend = 'Report Sheet Template Details'

    @button.buttonAndHandler(_('Submit'), name='add')
    def handleAdd(self, action):
        super(FlourishReportSheetAddView, self).handleAdd.func(self, action)

    @button.buttonAndHandler(_("Cancel"))
    def handle_cancel_action(self, action):
        self.request.response.redirect(self.nextURL())

    def create(self, data):
        worksheet = ReportWorksheet(data['title'])
        return worksheet

    def add(self, worksheet):
        chooser = INameChooser(self.context)
        name = chooser.chooseName(worksheet.title, worksheet)
        self.context[name] = worksheet
        return worksheet

    def nextURL(self):
        return absoluteURL(self.context, self.request)


class FlourishReportSheetEditView(flourish.form.Form, form.EditForm):

    template = InheritTemplate(flourish.page.Page.template)
    label = None
    legend = _('Report Sheet Template Information')
    fields = field.Fields(IReportWorksheet).select('title')

    @property
    def title(self):
        return self.context.title

    def update(self):
        return form.EditForm.update(self)

    @button.buttonAndHandler(_('Submit'), name='apply')
    def handleApply(self, action):
        super(FlourishReportSheetEditView, self).handleApply.func(self, action)
        # XXX: hacky sucessful submit check
        if (self.status == self.successMessage or
            self.status == self.noChangesMessage):
            self.request.response.redirect(self.nextURL())

    @button.buttonAndHandler(_("Cancel"))
    def handle_cancel_action(self, action):
        self.request.response.redirect(self.nextURL())

    def nextURL(self):
        return absoluteURL(self.context.__parent__, self.request)


def ReportScoreSystemsVocabulary(context):
    terms = [SimpleVocabulary.createTerm('ranged', 'ranged',
                                         _('-- Use range below --'))]
    for name, ss in sorted(getUtilitiesFor(IScoreSystem, context)):
        token = name.encode('punycode')
        term = SimpleVocabulary.createTerm(ss, token, ss.title)
        terms.append(term)
    for term in DiscreteScoreSystemsVocabulary(context):
        terms.append(term)
    return SimpleVocabulary(terms)


class IReportScoreSystem(Interface):
    """A schema used to choose an existing score system."""

    scoresystem = Choice(
        title=_('Score System'),
        description=_('Choose an existing score system or use range below'),
        vocabulary='schooltool.gradebook.reportscoresystems',
        required=True)

    min = Int(
        title=_("Minimum"),
        description=_("Lowest integer score value possible"),
        min=0,
        required=False)

    max = Int(
        title=_("Maximum"),
        description=_("Highest integer score value possible"),
        min=0,
        required=False)


class ReportScoresSystem(object):
    implements(IReportScoreSystem)
    adapts(IReportActivity)

    def __init__(self, context):
        self.__dict__['context'] = context

    def isRanged(self, ss):
        return (IRangedValuesScoreSystem.providedBy(ss) and
                ss.title == 'generated')

    def getValue(self, name, default):
        if default is None:
            default = 0
        value = self.__dict__.get(name, default)
        if value is None:
            return default
        return value

    def __setattr__(self, name, value):
        self.__dict__[name] = value
        ss = self.context.scoresystem

        if name == 'scoresystem':
            if value == 'ranged':
                if self.isRanged(ss):
                    minimum = self.getValue('min', ss.min)
                    maximum = self.getValue('max', ss.max)
                else:
                    minimum = self.getValue('min', 0)
                    maximum = self.getValue('max', 100)
                self.context.scoresystem = RangedValuesScoreSystem(u'generated', 
                    min=minimum, max=maximum)
            else:
                self.context.scoresystem = value

        else: # min, max
            if self.isRanged(ss):
                minimum = self.getValue('min', ss.min)
                maximum = self.getValue('max', ss.max)
                self.context.scoresystem = RangedValuesScoreSystem(u'generated', 
                    min=minimum, max=maximum)

    def __getattr__(self, name):
        ss = self.context.scoresystem
        if ss is None:
            return None
        rv = None
        if self.isRanged(ss):
            if name == 'scoresystem':
                rv = 'ranged'
            elif name == 'min':
                rv = ss.min
            elif name == 'max':
                rv = ss.max
        else:
            if name == 'scoresystem':
                rv = ss
        return rv


class ReportActivityAddView(form.AddForm):
    """A view for adding an activity."""
    label = _("Add new report activity")
    template = ViewPageTemplateFile('templates/add_edit_report_activity.pt')

    fields = field.Fields(IReportActivity)
    fields = fields.select('title', 'label', 'description')
    fields += field.Fields(IReportScoreSystem)

    def updateActions(self):
        super(ReportActivityAddView, self).updateActions()
        self.actions['add'].addClass('button-ok')
        self.actions['cancel'].addClass('button-cancel')

    @button.buttonAndHandler(_('Add'), name='add')
    def handleAdd(self, action):
        data, errors = self.extractData()
        if errors:
            self.status = self.formErrorsMessage
            return
        obj = self.createAndAdd(data)
        if obj is not None:
            # mark only as finished if we get the new object
            self._finishedAdd = True

    @button.buttonAndHandler(_("Cancel"))
    def handle_cancel_action(self, action):
        url = absoluteURL(self.context, self.request)
        self.request.response.redirect(url)

    def create(self, data):
        categories = getCategories(ISchoolToolApplication(None))
        if data['scoresystem'] == 'ranged':
            minimum = data['min']
            if minimum is None:
                minimum = 0
            maximum = data['max']
            if maximum is None:
                maximum = 100
            scoresystem = RangedValuesScoreSystem(u'generated', 
                min=minimum, max=maximum)
        else:
            scoresystem = data['scoresystem']
        activity = ReportActivity(data['title'], categories.getDefaultKey(), 
                                  scoresystem, data['description'],
                                  data['label'])
        return activity

    def add(self, activity):
        """Add activity to the worksheet."""
        chooser = INameChooser(self.context)
        name = chooser.chooseName('', activity)
        self.context[name] = activity
        return activity

    def nextURL(self):
        return absoluteURL(self.context, self.request)


class ReportActivityEditView(form.EditForm):
    """Edit form for basic person."""
    form.extends(form.EditForm)
    template = ViewPageTemplateFile('templates/add_edit_report_activity.pt')

    fields = field.Fields(IReportActivity)
    fields = fields.select('title', 'label', 'description')
    fields += field.Fields(IReportScoreSystem)

    @button.buttonAndHandler(_("Cancel"))
    def handle_cancel_action(self, action):
        self.request.response.redirect(self.nextURL())

    def updateActions(self):
        super(ReportActivityEditView, self).updateActions()
        self.actions['apply'].addClass('button-ok')
        self.actions['cancel'].addClass('button-cancel')

    def applyChanges(self, data):
        super(ReportActivityEditView, self).applyChanges(data)
        self.request.response.redirect(self.nextURL())

    @property
    def label(self):
        return _(u'Change information for ${fullname}',
                 mapping={'fullname': self.context.title})

    def nextURL(self):
        return absoluteURL(self.context.__parent__, self.request)


ApplyLabel = button.StaticButtonActionAttribute(
    _('Apply'),
    button=ReportActivityEditView.buttons['apply'])


class DeployReportWorksheetBaseView(object):
    """The base class for deploying a report sheet template"""

    @property
    def worksheets(self):
        """Get  a list of all report worksheets."""
        root = IGradebookRoot(ISchoolToolApplication(None))
        for worksheet in root.templates.values():
            yield {'name': getName(worksheet),
                   'title': worksheet.title}

    def update(self):
        root = IGradebookRoot(ISchoolToolApplication(None))
        if not root.templates:
            next_url = absoluteURL(ISchoolToolApplication(None), self.request)
            next_url += '/no_report_sheets.html'
            self.request.response.redirect(next_url)
            return
        if 'form-submitted' in self.request:
            if 'DEPLOY' in self.request:
                self.deploy()
            self.request.response.redirect(self.nextURL())

    def nextURL(self):
        return absoluteURL(self.context, self.request)

    def deployTerm(self, term):
        root = IGradebookRoot(ISchoolToolApplication(None))
        worksheet = root.templates[self.request['reportWorksheet']]

        # copy worksheet template to the term
        schoolyear = ISchoolYear(term)
        deployedKey = '%s_%s' % (schoolyear.__name__, term.__name__)
        deployedWorksheet = Worksheet(worksheet.title)
        chooser = INameChooser(root.deployed)
        name = chooser.chooseName(deployedKey, deployedWorksheet)
        root.deployed[name] = deployedWorksheet
        copyActivities(worksheet, deployedWorksheet)

        # now copy the template to all sections in the term
        sections = ISectionContainer(term)
        for section in sections.values():
            activities = IActivities(section)
            worksheetCopy = Worksheet(deployedWorksheet.title)
            worksheetCopy.deployed = True
            activities[deployedWorksheet.__name__] = worksheetCopy
            copyActivities(deployedWorksheet, worksheetCopy)


class DeployReportWorksheetSchoolYearView(DeployReportWorksheetBaseView):
    """A view for deploying a report sheet template to a schoolyear"""

    def deploy(self):
        for term in self.context.values():
            self.deployTerm(term)


class DeployReportWorksheetTermView(DeployReportWorksheetBaseView):
    """A view for deploying a report sheet template to a term"""

    def deploy(self):
        self.deployTerm(self.context)


class LayoutReportCardView(object):
    """A view for laying out the columns of the schoolyear's report card"""

    @property
    def columns(self):
        """Get  a list of the existing layout columns."""
        results = []
        root = IGradebookRoot(ISchoolToolApplication(None))
        schoolyearKey = self.context.__name__
        if schoolyearKey in root.layouts:
            current_columns = root.layouts[schoolyearKey].columns
        else:
            current_columns  = []
        for index, column in enumerate(current_columns):
            result = {
                'source_name': 'Column%s' % (index + 1),
                'source_value': column.source,
                'heading_name': 'Heading%s' % (index + 1),
                'heading_value': column.heading,
                }
            results.append(result)
        return results

    @property
    def outline_activities(self):
        """Get  a list of the existing layout outline activities."""
        results = []
        root = IGradebookRoot(ISchoolToolApplication(None))
        schoolyearKey = self.context.__name__
        if schoolyearKey in root.layouts:
            current_activities = root.layouts[schoolyearKey].outline_activities
        else:
            current_activities  = []
        for index, activity in enumerate(current_activities):
            result = {
                'source_name': 'Activity%s' % (index + 1),
                'source_value': activity.source,
                'heading_name': 'ActivityHeading%s' % (index + 1),
                'heading_value': activity.heading,
                }
            results.append(result)
        return results

    @property
    def column_choices(self):
        return self.choices(no_journal=False)

    @property
    def activity_choices(self):
        return self.choices(no_comment=False)

    def choices(self, no_comment=True, no_journal=True):
        """Get  a list of the possible choices for layout activities."""
        results = []
        root = IGradebookRoot(ISchoolToolApplication(None))
        for term in self.context.values():
            deployedKey = '%s_%s' % (self.context.__name__, term.__name__)
            for key in root.deployed:
                if key.startswith(deployedKey):
                    deployedWorksheet = root.deployed[key]
                    for activity in deployedWorksheet.values():
                        if ICommentScoreSystem.providedBy(activity.scoresystem):
                            if no_comment: 
                                continue
                        name = '%s - %s - %s' % (term.title,
                            deployedWorksheet.title, activity.title)
                        value = '%s|%s|%s' % (term.__name__,
                            deployedWorksheet.__name__, activity.__name__)
                        result = {
                            'name': name,
                            'value': value,
                            }
                        results.append(result)
        if not no_journal:
            result = {
                'name': ABSENT_HEADING,
                'value': ABSENT_KEY,
                }
            results.append(result)
            result = {
                'name': TARDY_HEADING,
                'value': TARDY_KEY,
                }
            results.append(result)
        return results

    def update(self):
        if 'form-submitted' in self.request:
            columns = self.updatedColumns()
            outline_activities = self.updatedOutlineActivities()

            root = IGradebookRoot(ISchoolToolApplication(None))
            schoolyearKey = self.context.__name__
            if schoolyearKey not in root.layouts:
                if not len(columns):
                    return
                root.layouts[schoolyearKey] = ReportLayout()
            layout = root.layouts[schoolyearKey]
            layout.columns = columns
            layout.outline_activities = outline_activities

            if 'OK' in self.request:
                self.request.response.redirect(self.nextURL())

    def updatedColumns(self):
        columns = []
        index = 1
        while True:
            source_name = 'Column%s' % index
            heading_name = 'Heading%s' % index
            index += 1
            if source_name not in self.request:
                break
            if 'delete_' + source_name in self.request:
                continue
            column = ReportColumn(self.request[source_name], 
                                  self.request[heading_name])
            columns.append(column)
        source_name = self.request['new_source']
        if 'ADD_COLUMN' in self.request and len(source_name):
            column = ReportColumn(source_name, '')
            columns.append(column)
        return columns

    def updatedOutlineActivities(self):
        activities = []
        index = 1
        while True:
            source_name = 'Activity%s' % index
            heading_name = 'ActivityHeading%s' % index
            index += 1
            if source_name not in self.request:
                break
            if 'delete_' + source_name in self.request:
                continue
            column = OutlineActivity(self.request[source_name], 
                                     self.request[heading_name])
            activities.append(column)
        source_name = self.request['new_activity_source']
        if 'ADD_ACTIVITY' in self.request and len(source_name):
            column = OutlineActivity(source_name, '')
            activities.append(column)
        return activities

    def nextURL(self):
        return absoluteURL(self.context, self.request)


class SectionAddedSubscriber(ObjectEventAdapterSubscriber):
    """Make sure the same worksheets are deployed to newly added
    sections."""

    adapts(IObjectAddedEvent, ISection)

    def __call__(self):
        root = IGradebookRoot(ISchoolToolApplication(None))
        activities = IActivities(self.object)
        term = ITerm(self.object)
        schoolyear = ISchoolYear(term)
        deployedKey = '%s_%s' % (schoolyear.__name__, term.__name__)
        for key in root.deployed:
            if key.startswith(deployedKey):
                deployedWorksheet = root.deployed[key]
                worksheetCopy = Worksheet(deployedWorksheet.title)
                worksheetCopy.deployed = True
                activities[key] = worksheetCopy
                copyActivities(deployedWorksheet, worksheetCopy)
