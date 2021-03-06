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
"""
Report Card Views
"""

from zope.component import getUtilitiesFor
from zope.schema.vocabulary import SimpleVocabulary
from zope.container.interfaces import INameChooser
from zope.browserpage.viewpagetemplatefile import ViewPageTemplateFile
from zope.component import adapts
from zope.interface import Interface, implements
from zope.lifecycleevent.interfaces import IObjectRemovedEvent
from zope.schema import Choice, Int
from zope.security.checker import canWrite
from zope.security.interfaces import Unauthorized
from zope.traversing.api import getName
from zope.traversing.browser.absoluteurl import absoluteURL
from zope.lifecycleevent.interfaces import IObjectAddedEvent
from zope.i18n import translate

from z3c.form import form, field, button

from schooltool.app.browser.app import ActiveSchoolYearContentMixin
from schooltool.app.interfaces import ISchoolToolApplication
from schooltool.gradebook import GradebookMessage as _
from schooltool.common.inlinept import InheritTemplate
from schooltool.common.inlinept import InlineViewPageTemplate
from schooltool.course.interfaces import ISectionContainer, ISection
from schooltool.person.interfaces import IPerson
from schooltool.schoolyear.interfaces import ISchoolYear
from schooltool.schoolyear.interfaces import ISchoolYearContainer
from schooltool.skin import flourish
from schooltool.skin.flourish.page import TertiaryNavigationManager
from schooltool.term.interfaces import ITerm
from schooltool.term.term import listTerms
from schooltool.schoolyear.subscriber import ObjectEventAdapterSubscriber

from schooltool.gradebook.interfaces import (IGradebookRoot,
    IGradebookTemplates, IReportWorksheet, IReportActivity, IActivities)
from schooltool.gradebook.activity import (Worksheet, Activity, ReportWorksheet,
    ReportActivity)
from schooltool.gradebook.browser.activity import FlourishWeightCategoriesView
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
AVERAGE_HEADING = _('Average')
ABSENT_ABBREVIATION = _('A')
TARDY_ABBREVIATION = _('T')
ABSENT_KEY = 'absent'
TARDY_KEY = 'tardy'
AVERAGE_KEY = '__average__'


def copyActivities(sourceWorksheet, destWorksheet):
    """Copy the activities and the category weights from the source worksheet
       to the destination."""

    for key, activity in sourceWorksheet.items():
        activityCopy = Activity(activity.title, activity.category,
                                activity.scoresystem, activity.description,
                                activity.label)
        destWorksheet[key] = activityCopy
    for category, weight in sourceWorksheet.getCategoryWeights().items():
        destWorksheet.setCategoryWeight(category, weight)


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


class FlourishReportSheetActionLinks(flourish.page.RefineLinksViewlet):
    """flourish Report Sheet Action links viewlet."""

    body_template = InlineViewPageTemplate("""
        <ul tal:attributes="class view/list_class">
          <li tal:repeat="item view/renderable_items"
              tal:attributes="class item/class"
              tal:content="structure item/viewlet">
          </li>
        </ul>
    """)

    # We don't want this manager rendered at all
    # if there are no renderable viewlets
    @property
    def renderable_items(self):
        result = []
        for item in self.items:
            render_result = item['viewlet']()
            if render_result and render_result.strip():
                result.append({
                        'class': item['class'],
                        'viewlet': render_result,
                        })
        return result

    def render(self):
        if self.renderable_items:
            return super(FlourishReportSheetActionLinks, self).render()


class HideUnhideReportSheetsLink(flourish.page.LinkViewlet,
                                 ActiveSchoolYearContentMixin):

    @property
    def enabled(self):
        if not self.view.all_sheets():
            return False
        return super(HideUnhideReportSheetsLink, self).enabled

    @property
    def url(self):
        url = '%s/hide_unhide_report_sheets.html?schoolyear_id=%s' % (
            absoluteURL(ISchoolToolApplication(None), self.request),
            self.schoolyear.__name__)
        return url


class FlourishReportSheetsBase(ActiveSchoolYearContentMixin):

    def sheets(self):
        return [sheet for sheet in self.all_sheets() if sheet['checked']]

    def all_sheets(self):
        if self.has_schoolyear:
            root = IGradebookRoot(ISchoolToolApplication(None))
            schoolyear = self.schoolyear
            deployments = {}
            for sheet in root.deployed.values():
                if not sheet.__name__.startswith(schoolyear.__name__):
                    continue
                index = int(sheet.__name__[sheet.__name__.rfind('_') + 1:])
                deployment = deployments.setdefault(index, {
                    'obj': sheet,
                    'index': str(index),
                    'checked': not sheet.hidden,
                    'terms': [False] * len(schoolyear),
                    })
                for index, term in enumerate(listTerms(schoolyear)):
                    deployedKey = '%s_%s' % (schoolyear.__name__, term.__name__)
                    if sheet.__name__.startswith(deployedKey):
                        deployment['terms'][index] = True
            sheets = [v for k, v in sorted(deployments.items())]
            return ([sheet for sheet in sheets if sheet['checked']] +
                    [sheet for sheet in sheets if not sheet['checked']])
        else:
            return []


class FlourishManageReportSheetTemplatesOverview(FlourishReportSheetsBase,
                                                 flourish.page.Content):
    """A flourish viewlet for showing report sheet templates in school view"""

    body_template = ViewPageTemplateFile(
        'templates/f_manage_report_sheet_templates_overview.pt')

    @property
    def templates(self):
        root = IGradebookRoot(ISchoolToolApplication(None))
        return list(root.templates.values())

    def templates_url(self):
        return self.url_with_schoolyear_id(self.context,
                                           view_name='gradebook/templates')


class FlourishManageReportSheetsOverview(FlourishReportSheetsBase,
                                         flourish.page.Content):
    """A flourish viewlet for showing deployed report sheets in school view"""

    body_template = ViewPageTemplateFile(
        'templates/f_manage_report_sheets_overview.pt')

    def sheets_url(self):
        return self.url_with_schoolyear_id(self.context,
                                           view_name='report_sheets')


class FlourishReportSheetsView(FlourishReportSheetsBase, flourish.page.Page):
    """A flourish view for managing report sheet deployment"""

    def __init__(self, context, request):
        super(FlourishReportSheetsView, self).__init__(context, request)
        self.alternate_title = self.request.get('alternate_title')

    @property
    def title(self):
        title = _(u'Report Sheets for ${year}',
                  mapping={'year': self.schoolyear.title})
        return translate(title, context=self.request)

    @property
    def has_error(self):
        return self.no_template or self.no_title

    @property
    def no_template(self):
        return 'SUBMIT' in self.request and not self.request.get('template')

    @property
    def no_title(self):
        return ('SUBMIT' in self.request and
                not self.request.get('alternate_title'))

    @property
    def terms(self):
        result = [{
            'name': '',
            'title': _('-- Entire year --'),
            'selected': 'selected',
            }]
        for term in listTerms(self.schoolyear):
            result.append({
                'name': term.__name__,
                'title': term.title,
                'selected': '',
                })
        return result

    @property
    def templates(self):
        result = [{
            'name': '',
            'title': _('-- Select a template --'),
            'selected': 'selected',
            }]
        root = IGradebookRoot(ISchoolToolApplication(None))
        for template in root.templates.values():
            result.append({
                'name': template.__name__,
                'title': template.title,
                'selected': '',
                })
        return result

    def update(self):
        if 'CANCEL' in self.request:
            self.request.response.redirect(self.nextURL())
        if 'SUBMIT' in self.request:
            if self.request.get('template') and self.alternate_title:
                root = IGradebookRoot(ISchoolToolApplication(None))
                template = root.templates[self.request['template']]
                term = self.request.get('term')
                if term:
                    term = self.schoolyear[term]
                self.deploy(term, template)
                self.alternate_title = ''

    def deploy(self, term, template):
        # get the next index and title
        root = IGradebookRoot(ISchoolToolApplication(None))
        schoolyear, highest, title_index = self.schoolyear, 0, 0
        template_title = self.alternate_title
        for sheet in root.deployed.values():
            if not sheet.__name__.startswith(schoolyear.__name__):
                continue
            index = int(sheet.__name__[sheet.__name__.rfind('_') + 1:])
            if index > highest:
                highest = index
            if sheet.title.startswith(template_title):
                rest = sheet.title[len(template_title):]
                if not rest:
                    new_index = 1
                elif len(rest) > 1 and rest[0] == '-' and rest[1:].isdigit():
                    new_index = int(rest[1:])
                else:
                    new_index = 0
                if new_index > title_index:
                    title_index = new_index

        # copy worksheet template to the term or whole year
        if term:
            terms = [term]
        else:
            terms = schoolyear.values()
        for term in terms:
            deployedKey = '%s_%s_%s' % (schoolyear.__name__, term.__name__,
                                        highest + 1)
            title = template_title
            if title_index:
                title += '-%s' % (title_index + 1)
            deployedWorksheet = Worksheet(title)
            root.deployed[deployedKey] = deployedWorksheet
            copyActivities(template, deployedWorksheet)

            # now copy the template to all sections in the term
            sections = ISectionContainer(term)
            for section in sections.values():
                activities = IActivities(section)
                worksheetCopy = Worksheet(deployedWorksheet.title)
                worksheetCopy.deployed = True
                activities[deployedWorksheet.__name__] = worksheetCopy
                copyActivities(deployedWorksheet, worksheetCopy)

    def nextURL(self):
        return self.url_with_schoolyear_id(self.context, view_name='manage')


class ReportSheetsTertiaryNavigationManager(ActiveSchoolYearContentMixin,
                                            TertiaryNavigationManager):

    template = InlineViewPageTemplate("""
        <ul tal:attributes="class view/list_class">
          <li tal:repeat="item view/items"
              tal:attributes="class item/class"
              tal:content="structure item/viewlet">
          </li>
        </ul>
    """)

    @property
    def items(self):
        result = []
        active = self.schoolyear
        for schoolyear in ISchoolYearContainer(self.context).values():
            url = '%s/report_sheets?schoolyear_id=%s' % (
                absoluteURL(self.context, self.request),
                schoolyear.__name__)
            result.append({
                'class': schoolyear.first == active.first and 'active' or None,
                'viewlet': u'<a href="%s">%s</a>' % (url, schoolyear.title),
                })
        return result


class FlourishHideUnhideReportSheetsView(FlourishReportSheetsBase,
                                         flourish.page.Page):
    """A flourish view for hiding/unhiding report sheet deployments"""

    @property
    def title(self):
        title = _(u'Hide/unhide Report Sheets for ${year}',
                  mapping={'year': self.schoolyear.title})
        return translate(title, context=self.request)

    @property
    def terms(self):
        return listTerms(self.schoolyear)

    def update(self):
        if 'CANCEL' in self.request:
            self.request.response.redirect(self.nextURL())
        elif 'SUBMIT' in self.request:
            visible = self.request.get('visible', [])
            root = IGradebookRoot(ISchoolToolApplication(None))
            schoolyear = self.schoolyear
            for sheet in root.deployed.values():
                if not sheet.__name__.startswith(schoolyear.__name__):
                    continue
                index = sheet.__name__[sheet.__name__.rfind('_') + 1:]
                self.handleSheet(sheet, index, visible)
            self.request.response.redirect(self.nextURL())

    def handleSheet(self, sheet, index, visible):
        if index not in visible and not sheet.hidden:
            sheet.hidden = True
        elif index in visible and sheet.hidden:
            sheet.hidden = False
        else:
            return
        schoolyear = self.schoolyear
        for term in schoolyear.values():
            deployedKey = '%s_%s_%s' % (schoolyear.__name__, term.__name__,
                                        index)
            if sheet.__name__ == deployedKey:
                for section in ISectionContainer(term).values():
                    activities = IActivities(section)
                    if deployedKey in activities:
                        activities[deployedKey].hidden = sheet.hidden
                return

    def nextURL(self):
        return self.url_with_schoolyear_id(self.context,
                                           view_name='report_sheets')


class FlourishTemplatesView(flourish.page.Page):
    """A flourish view for managing report sheet templates"""

    def update(self):
        if 'form-submitted' in self.request:
            for template in self.context.values():
                name = 'delete.%s' % template.__name__
                if name in self.request:
                    del self.context[template.__name__]
                    return
                for activity in template.values():
                    name = 'delete_activity.%s.%s' % (template.__name__,
                                                      activity.__name__)
                    if name in self.request:
                        del template[activity.__name__]
                        return


class FlourishReportSheetsOverviewLinks(flourish.page.RefineLinksViewlet):
    """flourish report sheet templates overview add links viewlet."""


class FlourishReportCardLayoutOverviewLinks(flourish.page.RefineLinksViewlet):
    """flourish report card layouts overview add links viewlet."""


class ReportSheetAddLinks(flourish.page.RefineLinksViewlet):
    """Report sheet add links viewlet."""


class ReportSheetSettingsLinks(flourish.page.RefineLinksViewlet):
    """Report sheet settings links viewlet."""


class ReportSheetWeightCategoriesView(FlourishWeightCategoriesView):
    """Report sheet category weights view."""

    def nextURL(self):
        return absoluteURL(self.context, self.request)


class FlourishReportSheetAddView(flourish.form.AddForm):
    """flourish view for adding a report sheet template."""

    fields = field.Fields(IReportWorksheet).select('title')
    template = InheritTemplate(flourish.page.Page.template)
    label = None
    legend = _('Report Sheet Template Details')

    @button.buttonAndHandler(_('Submit'), name='add')
    def handleAdd(self, action):
        super(FlourishReportSheetAddView, self).handleAdd.func(self, action)

    @button.buttonAndHandler(_("Cancel"))
    def handle_cancel_action(self, action):
        url = absoluteURL(self.context, self.request)
        self.request.response.redirect(url)

    def create(self, data):
        worksheet = ReportWorksheet(data['title'])
        return worksheet

    def add(self, worksheet):
        chooser = INameChooser(self.context)
        name = chooser.chooseName(worksheet.title, worksheet)
        self.context[name] = worksheet
        self._worksheet = worksheet
        return worksheet

    def nextURL(self):
        return absoluteURL(self._worksheet, self.request)

    def updateActions(self):
        super(FlourishReportSheetAddView, self).updateActions()
        self.actions['add'].addClass('button-ok')
        self.actions['cancel'].addClass('button-cancel')


class FlourishReportSheetEditView(flourish.form.Form, form.EditForm):

    template = InheritTemplate(flourish.page.Page.template)
    label = None
    legend = _('Report Sheet Template Information')
    fields = field.Fields(IReportWorksheet).select('title')

    @property
    def title(self):
        return self.context.title

    def display_scoresystem(self, activity):
        ss = activity.scoresystem
        if IRangedValuesScoreSystem.providedBy(ss):
            return '%s - %s' % (ss.min, ss.max)
        return ss.title

    def update(self):
        if 'form-submitted' in self.request:
            for activity in self.context.values():
                name = 'delete.%s' % activity.__name__
                if name in self.request:
                    del self.context[activity.__name__]
                    break
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

    def updateActions(self):
        super(FlourishReportSheetEditView, self).updateActions()
        self.actions['apply'].addClass('button-ok')
        self.actions['cancel'].addClass('button-cancel')


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

    max = Int(
        title=_("Maximum"),
        description=_("Highest integer score value possible"),
        min=0,
        required=False)

    min = Int(
        title=_("Minimum"),
        description=_("Lowest integer score value possible"),
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
    fields = fields.select('title', 'label', 'description', 'category')
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
        activity = ReportActivity(data['title'], data['category'], 
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


class FlourishReportActivityAddView(ReportActivityAddView,
                                    flourish.form.AddForm):
    """A flourish view for adding a report activity."""

    template = InheritTemplate(flourish.page.Page.template)
    label = None
    legend = _('Report Activity Details')
    formErrorsMessage = _('Please correct the marked fields below.')

    @button.buttonAndHandler(_('Submit'), name='add')
    def handleAdd(self, action):
        super(FlourishReportActivityAddView, self).handleAdd.func(self, action)

    @button.buttonAndHandler(_("Cancel"))
    def handle_cancel_action(self, action):
        self.request.response.redirect(self.nextURL())

    def nextURL(self):
        return absoluteURL(self.context, self.request)


class ReportActivityEditView(form.EditForm):
    """Edit form for basic person."""
    form.extends(form.EditForm)
    template = ViewPageTemplateFile('templates/add_edit_report_activity.pt')

    fields = field.Fields(IReportActivity)
    fields = fields.select('title', 'label', 'description', 'category')
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


class FlourishReportActivityEditView(ReportActivityEditView,
                                     flourish.form.Form):
    """A flourish view for editing a report activity."""

    template = InheritTemplate(flourish.page.Page.template)
    label = None
    legend = _('Report Activity Details')
    formErrorsMessage = _('Please correct the marked fields below.')

    @button.buttonAndHandler(_('Submit'), name='apply')
    def handleApply(self, action):
        super(FlourishReportActivityEditView, self).handleApply.func(self, action)
        # XXX: hacky sucessful submit check
        if (self.status == self.successMessage or
            self.status == self.noChangesMessage):
            self.request.response.redirect(self.nextURL())

    @button.buttonAndHandler(_("Cancel"))
    def handle_cancel_action(self, action):
        self.request.response.redirect(self.nextURL())

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


class HideReportWorksheetView(object):
    """A view for hiding a report sheet that is deployed in a term"""

    @property
    def worksheets(self):
        """Get a list of all deployed report worksheets that are not hidden."""
        root = IGradebookRoot(ISchoolToolApplication(None))
        schoolyear = ISchoolYear(self.context)
        deployedKey = '%s_%s' % (schoolyear.__name__, self.context.__name__)
        for key, worksheet in sorted(root.deployed.items()):
            if worksheet.hidden:
                continue
            if key.startswith(deployedKey):
                yield {
                    'name': key,
                    'title': worksheet.title
                    }

    def update(self):
        self.available = bool(list(self.worksheets))
        self.confirm = self.request.get('confirm')
        self.confirm_title = ''
        root = IGradebookRoot(ISchoolToolApplication(None))
        if 'CANCEL' in self.request:
            self.request.response.redirect(self.nextURL())
        elif 'HIDE' in self.request:
            if not self.confirm:
                self.confirm = self.request['reportWorksheet']
                self.confirm_title = root.deployed[self.confirm].title
            else:
                worksheet = root.deployed[self.confirm]
                worksheet.hidden = True
                sections = ISectionContainer(self.context)
                for section in sections.values():
                    activities = IActivities(section)
                    activities[worksheet.__name__].hidden = True
                self.request.response.redirect(self.nextURL())

    def nextURL(self):
        return absoluteURL(self.context, self.request)


class UnhideReportWorksheetView(object):
    """A view for unhiding a deployed report sheet that is hidden"""

    @property
    def worksheets(self):
        """Get a list of all deployed report worksheets that are hidden."""
        root = IGradebookRoot(ISchoolToolApplication(None))
        schoolyear = ISchoolYear(self.context)
        deployedKey = '%s_%s' % (schoolyear.__name__, self.context.__name__)
        for key, worksheet in sorted(root.deployed.items()):
            if not worksheet.hidden:
                continue
            if key.startswith(deployedKey):
                yield {
                    'name': key,
                    'title': worksheet.title
                    }

    def update(self):
        self.available = bool(list(self.worksheets))
        self.confirm = self.request.get('confirm')
        self.confirm_title = ''
        root = IGradebookRoot(ISchoolToolApplication(None))
        if 'CANCEL' in self.request:
            self.request.response.redirect(self.nextURL())
        elif 'UNHIDE' in self.request:
            if not self.confirm:
                self.confirm = self.request['reportWorksheet']
                self.confirm_title = root.deployed[self.confirm].title
            else:
                worksheet = root.deployed[self.confirm]
                worksheet.hidden = False
                sections = ISectionContainer(self.context)
                for section in sections.values():
                    activities = IActivities(section)
                    activities[worksheet.__name__].hidden = False
                self.request.response.redirect(self.nextURL())

    def nextURL(self):
        return absoluteURL(self.context, self.request)


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


class LayoutReportCardLink(flourish.page.LinkViewlet,
                           ActiveSchoolYearContentMixin):

    @property
    def title(self):
        if self.schoolyear is None:
            return ''
        return _("Report Card Layout")

    @property
    def url(self):
        return self.url_with_schoolyear_id(self.context, view_name=self.link)


class FlourishLayoutReportCardView(flourish.page.Page,
                                   ActiveSchoolYearContentMixin):
    """A flourish view for laying out the columns of the report card"""

    def __init__(self, context, request):
        super(FlourishLayoutReportCardView, self).__init__(context, request)
        if self.schoolyear is None:
            self.request.response.redirect(self.nextURL())

    @property
    def title(self):
        title = _(u'Report Card Layout for ${year}',
                  mapping={'year': self.schoolyear.title})
        return translate(title, context=self.request)

    def getSourceName(self, source):
        if source == ABSENT_KEY:
            return ABSENT_HEADING
        if source == TARDY_KEY:
            return TARDY_HEADING
        termName, worksheetName, activityName = source.split('|')
        term = self.schoolyear.get(termName)
        if term is None: # maybe term was deleted
            return
        root = IGradebookRoot(ISchoolToolApplication(None))
        worksheet = root.deployed[worksheetName]
        if activityName == AVERAGE_KEY:
            activity_title = AVERAGE_HEADING
        else:
            activity_title = worksheet[activityName].title
        return '%s - %s - %s' % (term.title, worksheet.title, activity_title)

    def getEditURL(self, source_type, index):
        return '%s/editReportCard%s.html?schoolyear_id=%s&source_index=%s' % (
            absoluteURL(self.context, self.request), source_type,
            self.schoolyear.__name__, index + 1)
 
    def nextURL(self):
        return self.url_with_schoolyear_id(self.context, view_name='manage')

    @property
    def columns(self):
        """Get  a list of the existing layout columns."""
        results = []
        root = IGradebookRoot(ISchoolToolApplication(None))
        schoolyearKey = self.schoolyear.__name__
        if schoolyearKey in root.layouts:
            current_columns = root.layouts[schoolyearKey].columns
        else:
            current_columns  = []
        for index, column in enumerate(current_columns):
            sourceName = self.getSourceName(column.source)
            if sourceName is None:
                continue
            result = {
                'source_index': index + 1,
                'source_value': sourceName,
                'source_edit': self.getEditURL('Column', index),
                'heading_value': column.heading,
                }
            results.append(result)
        return results

    @property
    def outline_activities(self):
        """Get  a list of the existing layout outline activities."""
        results = []
        root = IGradebookRoot(ISchoolToolApplication(None))
        schoolyearKey = self.schoolyear.__name__
        if schoolyearKey in root.layouts:
            current_activities = root.layouts[schoolyearKey].outline_activities
        else:
            current_activities  = []
        for index, activity in enumerate(current_activities):
            sourceName = self.getSourceName(activity.source)
            if sourceName is None:
                continue
            result = {
                'source_index': index + 1,
                'source_value': sourceName,
                'source_edit': self.getEditURL('Activity', index),
                'heading_value': activity.heading,
                }
            results.append(result)
        return results

    def update(self):
        if not self.has_schoolyear:
            return

        root = IGradebookRoot(ISchoolToolApplication(None))
        year_id = self.schoolyear.__name__
        if year_id not in root.layouts:
            root.layouts[year_id] = ReportLayout()
        layout = root.layouts[year_id]

        columns = layout.columns
        for index in range(len(columns)):
            delete_key = 'delete_column.%s' % (index + 1)
            if delete_key in self.request:
                columns.pop(index)
                layout.columns = columns
                return

        activities = layout.outline_activities
        for index in range(len(activities)):
            delete_key = 'delete_activity.%s' % (index + 1)
            if delete_key in self.request:
                activities.pop(index)
                layout.outline_activities = activities
                return


class LayoutReportCardTertiaryNavigationManager(
    ActiveSchoolYearContentMixin, flourish.viewlet.ViewletManager):

    template = InlineViewPageTemplate("""
        <ul tal:attributes="class view/list_class">
          <li tal:repeat="item view/items"
              tal:attributes="class item/class"
              tal:content="structure item/viewlet">
          </li>
        </ul>
    """)

    list_class = 'third-nav'

    @property
    def items(self):
        result = []
        active = self.schoolyear
        for schoolyear in ISchoolYearContainer(self.context).values():
            url = '%s/report_card_layout?schoolyear_id=%s' % (
                absoluteURL(self.context, self.request),
                schoolyear.__name__)
            result.append({
                'class': schoolyear.first == active.first and 'active' or None,
                'viewlet': u'<a href="%s">%s</a>' % (url, schoolyear.title),
                })
        return result


class ReportCardColumnLinkViewlet(ActiveSchoolYearContentMixin,
                                  flourish.page.LinkViewlet):

    @property
    def link(self):
        return 'addReportCardColumn.html?schoolyear_id=%s' % (
            self.schoolyear.__name__)


class ReportCardActivityLinkViewlet(ActiveSchoolYearContentMixin,
                                    flourish.page.LinkViewlet):

    @property
    def link(self):
        return 'addReportCardActivity.html?schoolyear_id=%s' % (
            self.schoolyear.__name__)


class FlourishReportCardLayoutMixin(ActiveSchoolYearContentMixin):
    """A flourish mixin class for column or activity add/edit views"""

    @property
    def title(self):
        title = _(u'Report Card Layout for ${year}',
                  mapping={'year': self.schoolyear.title})
        return translate(title, context=self.request)

    @property
    def heading(self):
        source_obj = self.getSourceObj()
        return source_obj and source_obj.heading or ''

    def getSourceObj(self):
        source_index = int(self.request.get('source_index', '0'))
        if not source_index:
            return None
        root = IGradebookRoot(ISchoolToolApplication(None))
        year_id = self.schoolyear.__name__
        if year_id not in root.layouts:
            return None
        layout = root.layouts[year_id]
        if self.source_type == 'grid':
            sources = layout.columns
        else:
            sources = layout.outline_activities
        if source_index - 1 < len(sources):
            return sources[source_index - 1]
        else:
            return None

    def choices(self, no_comment=True, no_journal=True):
        """Get  a list of the possible choices for layout activities."""
        results = []
        source_obj = self.getSourceObj()
        if source_obj is None:
            source = ''
        else:
            source = source_obj.source
        root = IGradebookRoot(ISchoolToolApplication(None))
        for term in listTerms(self.schoolyear):
            deployedKey = '%s_%s' % (self.schoolyear.__name__, term.__name__)
            for key in root.deployed:
                if key.startswith(deployedKey):
                    deployedWorksheet = root.deployed[key]
                    if deployedWorksheet.hidden:
                        continue
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
                            'selected': value == source and 'selected' or None,
                            }
                        results.append(result)
                    if not no_journal:
                        name = '%s - %s - %s' % (term.title,
                            deployedWorksheet.title, AVERAGE_HEADING)
                        value = '%s|%s|%s' % (term.__name__,
                            deployedWorksheet.__name__, AVERAGE_KEY)
                        result = {
                            'name': name,
                            'value': value,
                            'selected': value == source and 'selected' or None,
                            }
                        results.append(result)
        if not no_journal:
            result = {
                'name': ABSENT_HEADING,
                'value': ABSENT_KEY,
                'selected': source == ABSENT_KEY and 'selected' or None,
                }
            results.append(result)
            result = {
                'name': TARDY_HEADING,
                'value': TARDY_KEY,
                'selected': source == TARDY_KEY and 'selected' or None,
                }
            results.append(result)
        return results

    def update(self):
        # this method handles add/edit of grid columns and outline items
        if 'CANCEL' in self.request or not self.has_schoolyear:
            self.request.response.redirect(self.nextURL())
        if 'UPDATE_SUBMIT' in self.request:
            if not self.request.get('source'):
                self.request.response.redirect(self.nextURL())
                return

            root = IGradebookRoot(ISchoolToolApplication(None))
            year_id = self.schoolyear.__name__
            if year_id not in root.layouts:
                root.layouts[year_id] = ReportLayout()
            layout = root.layouts[year_id]

            source_index = self.request.get('source_index')
            if source_index:
                source_index = int(source_index)
            else:
                source_index = 0
            if self.source_type == 'grid':
                columns = layout.columns
                column = ReportColumn(self.request['source'], 
                                      self.request['heading'])
                if source_index and source_index - 1 < len(layout.columns):
                    columns[source_index - 1] = column
                else:
                    columns.append(column)
                layout.columns = columns
            else:
                activities = layout.outline_activities
                activity = OutlineActivity(self.request['source'], 
                                           self.request['heading'])
                if (source_index and
                    source_index - 1 < len(layout.outline_activities)):
                    activities[source_index - 1] = activity
                else:
                    activities.append(activity)
                layout.outline_activities = activities

            self.request.response.redirect(self.nextURL())

    def nextURL(self):
        return self.url_with_schoolyear_id(self.context, view_name='report_card_layout')


class FlourishReportCardColumnBase(FlourishReportCardLayoutMixin):
    """A flourish base class for column add/edit views"""

    source_type = 'grid'

    @property
    def legend(self):
        return _('Grid Column Details')

    @property
    def source_label(self):
        return _('Grid column source')

    @property
    def heading_label(self):
        return _('Grid column heading')

    @property
    def source_choices(self):
        return self.choices(no_journal=False)


class FlourishReportCardActivityBase(FlourishReportCardLayoutMixin):
    """A flourish base class for outline activity add/edit views"""

    source_type = 'outline'

    @property
    def legend(self):
        return _('Outline Item Details')

    @property
    def source_label(self):
        return _('Outline item source')

    @property
    def heading_label(self):
        return _('Outline item heading')

    @property
    def source_choices(self):
        return self.choices(no_comment=False)


class FlourishReportCardColumnAddView(FlourishReportCardColumnBase,
                                      flourish.page.Page):
    """A flourish view for adding a column to the report card layout"""


class FlourishReportCardActivityEditView(FlourishReportCardActivityBase,
                                         flourish.page.Page):
    """A flourish view for adding an activity to  the report card layout"""


class FlourishReportCardColumnEditView(FlourishReportCardColumnBase,
                                       flourish.page.Page):
    """A flourish view for adding a column to the report card layout"""


class FlourishReportCardActivityAddView(FlourishReportCardActivityBase,
                                        flourish.page.Page):
    """A flourish view for adding an activity to  the report card layout"""


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
                worksheetCopy.hidden = deployedWorksheet.hidden
                activities[key] = worksheetCopy
                copyActivities(deployedWorksheet, worksheetCopy)


class RemoveLayoutColumnsWhenTermIsRemoved(ObjectEventAdapterSubscriber):

    adapts(IObjectRemovedEvent, ITerm)

    def __call__(self):
        return
        root = IGradebookRoot(ISchoolToolApplication(None))
        schoolyear = ISchoolYear(self.object)
        layout = root.layouts.get(schoolyear.__name__)
        if layout is not None:
            self.remove_term_columns(layout.columns)
            self.remove_term_columns(layout.outline_activities)

    def remove_term_columns(self, layout_columns):
        columns = layout_columns[:]
        for column in columns:
            source = column.source
            if source in (ABSENT_KEY, TARDY_KEY):
                continue
            termName, worksheetName, activityName = source.split('|')
            if termName == self.object.__name__:
                layout_columns.remove(column)
