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
SchoolBell calendar views.

$Id$
"""

from datetime import datetime, date, time, timedelta
import urllib
import calendar
import sys

from zope.app.form.browser.add import AddView
from zope.app.form.interfaces import ConversionError
from zope.app.form.interfaces import IWidgetInputError
from zope.app.form.interfaces import WidgetInputError, WidgetsError
from zope.app.form.utility import getWidgetsData
from zope.app.pagetemplate.viewpagetemplatefile import ViewPageTemplateFile
from zope.app.publisher.browser import BrowserView
from zope.app.traversing.browser.absoluteurl import absoluteURL
from zope.component import queryView, queryMultiAdapter, adapts
from zope.interface import implements, Interface
from zope.publisher.interfaces.browser import IBrowserPublisher
from zope.publisher.interfaces import NotFound
from zope.schema import Date, TextLine, Choice, Int, Bool, List, Text
from zope.schema.interfaces import RequiredMissing, ConstraintNotSatisfied
from zope.schema.vocabulary import SimpleVocabulary, SimpleTerm

from schoolbell.app.cal import CalendarEvent
from schoolbell.app.interfaces import ICalendarOwner, IContainedCalendarEvent
from schoolbell.calendar.interfaces import ICalendar, ICalendarEvent
from schoolbell.calendar.recurrent import DailyRecurrenceRule
from schoolbell.calendar.recurrent import DailyRecurrenceRule
from schoolbell.calendar.recurrent import YearlyRecurrenceRule
from schoolbell.calendar.recurrent import MonthlyRecurrenceRule
from schoolbell.calendar.recurrent import WeeklyRecurrenceRule
from schoolbell.calendar.utils import parse_date
from schoolbell.calendar.utils import parse_time, weeknum_bounds
from schoolbell.calendar.utils import week_start, prev_month, next_month
from schoolbell import SchoolBellMessageID as _


class CalendarOwnerTraverser(object):
    """A traverser that allows to traverse to a calendar owner's calendar."""

    adapts(ICalendarOwner)
    implements(IBrowserPublisher)

    def __init__(self, context, request):
        self.context = context
        self.request = request

    def publishTraverse(self, request, name):
        if name == 'calendar':
            return self.context.calendar
        elif name == 'calendar.ics':
            calendar = self.context.calendar
            view = queryMultiAdapter((calendar, request), name=name)
            if view is not None:
                return view

        view = queryMultiAdapter((self.context, request), name=name)
        if view is not None:
            return view

        raise NotFound(self.context, name, request)

    def browserDefault(self, request):
        return self.context, ('index.html', )


class CalendarTraverser(object):
    """A smart calendar traverser that can handle dates in the URL."""

    adapts(ICalendarOwner)
    implements(IBrowserPublisher)

    queryMultiAdapter = staticmethod(queryMultiAdapter)

    def __init__(self, context, request):
        self.context = context
        self.request = request

    def browserDefault(self, request):
        return self.context, ('daily.html', )

    def publishTraverse(self, request, name):
        view_name = self.getViewByDate(request, name)
        if view_name:
            return self.queryMultiAdapter((self.context, request),
                                          name=view_name)

        view = queryMultiAdapter((self.context, request), name=name)
        if view is not None:
            return view

        try:
            return self.context.find(name)
        except KeyError:
            raise NotFound(self.context, name, request)

    def getViewByDate(self, request, name):
        parts = name.split('-')

        if len(parts) == 2 and parts[1].startswith('w'): # a week was given
            try:
                year = int(parts[0])
                week = int(parts[1][1:])
            except ValueError:
                return
            request.form['date'] = self.getWeek(year, week).isoformat()
            return 'weekly.html'

        # a year, month or day might have been given
        try:
            parts = [int(part) for part in parts]
        except ValueError:
            return
        if not parts:
            return
        parts = tuple(parts)

        if not (1900 < parts[0] < 2100):
            return

        if len(parts) == 1:
            request.form['date'] = "%d-01-01" % parts
            return 'yearly.html'
        elif len(parts) == 2:
            request.form['date'] = "%d-%02d-01" % parts
            return 'monthly.html'
        elif len(parts) == 3:
            request.form['date'] = "%d-%02d-%02d" % parts
            return 'daily.html'

    def getWeek(self, year, week):
        """Get the start of a week by week number.

        The Monday of the given week is returned as a datetime.date.

            >>> traverser = CalendarTraverser(None, None)
            >>> traverser.getWeek(2002, 11)
            datetime.date(2002, 3, 11)
            >>> traverser.getWeek(2005, 1)
            datetime.date(2005, 1, 3)
            >>> traverser.getWeek(2005, 52)
            datetime.date(2005, 12, 26)

        """
        return weeknum_bounds(year, week)[0]


class CalendarDay(object):
    """A single day in a calendar.

    Attributes:
       'date'   -- date of the day (a datetime.date instance)
       'events' -- list of events that took place that day, sorted by start
                   time (in ascending order).
    """

    def __init__(self, date, events=None):
        self.date = date
        if events is None:
            self.events = []
        else:
            self.events = events

    def __cmp__(self, other):
        return cmp(self.date, other.date)


class PlainCalendarView(BrowserView):
    """A calendar view purely for testing purposes."""

    __used_for__ = ICalendar

    num_events = 5
    evt_range = 60*24*14 # two weeks

    def iterEvents(self):
        events = list(self.context)
        events.sort()
        return events

    def update(self):
        if 'GENERATE' in self.request:
            import random
            for i in range(self.num_events):
                delta = random.randint(-self.evt_range, self.evt_range)
                dtstart = datetime.now() + timedelta(minutes=delta)
                length = timedelta(minutes=random.randint(1, 60*12))
                title = 'Event %d' % random.randint(1, 999)

                # Events won't always have descriptions
                description = None
                if i % 2:
                    description = 'Description for %s' % title

                recurrence = None
                if i > 3:
                    interval = random.randint(1, 5)
                    count = random.randint(1, 10)
                    recurrence = DailyRecurrenceRule(interval=interval,
                                                     count=count)

                event = CalendarEvent(dtstart, length, title,
                        description=description, recurrence=recurrence)
                self.context.addEvent(event)


class CalendarViewBase(BrowserView):
    """A base class for the calendar views.

    This class provides functionality that is useful to several calendar views.
    """

    __used_for__ = ICalendar

    # XXX I'd rather these constants would go somewhere in schoolbell.calendar.
    month_names = {
        1: _("January"), 2: _("February"), 3: _("March"),
        4: _("April"), 5: _("May"), 6: _("June"),
        7: _("July"), 8: _("August"), 9: _("September"),
        10: _("October"), 11: _("November"), 12: _("December")}

    day_of_week_names = {
        0: _("Monday"), 1: _("Tuesday"), 2: _("Wednesday"), 3: _("Thursday"),
        4: _("Friday"), 5: _("Saturday"), 6: _("Sunday")}

    short_day_of_week_names = {
        0: _("Mon"), 1: _("Tue"), 2: _("Wed"), 3: _("Thu"),
        4: _("Fri"), 5: _("Sat"), 6: _("Sun"),
    }

    # Which day is considered to be the first day of the week (0 = Monday,
    # 6 = Sunday).  Currently hardcoded.
    first_day_of_week = 0

    def dayTitle(self, day):
        day_of_week = unicode(self.day_of_week_names[day.weekday()])
        return _('%s, %s') % (day_of_week, day.strftime('%Y-%m-%d'))

    __url = None

    def calURL(self, cal_type, cursor=None):
        """Construct a URL to a calendar at cursor."""
        if cursor is None:
            cursor = self.cursor
        if self.__url is None:
            self.__url = absoluteURL(self.context, self.request)

        if cal_type == 'daily':
            dt = cursor.isoformat()
        elif cal_type == 'weekly':
            dt = cursor.strftime('%G-w%V')
        elif cal_type == 'monthly':
            dt = cursor.strftime('%Y-%m')
        elif cal_type == 'yearly':
            dt = str(cursor.year)
        else:
            raise ValueError(cal_type)

        return  '%s/%s' % (self.__url, dt)

    def ellipsizeTitle(self, title):
        """For labels with limited space replace the tail with '...'."""
        if len(title) < 17:
             return title
        else:
             return title[:15] + '...'

    def update(self):
        if 'date' not in self.request:
            self.cursor = date.today()
        else:
            # It would be nice not to b0rk when the date is invalid but fall
            # back to the current date, as if the date had not been specified.
            self.cursor = parse_date(self.request['date'])

    def getWeek(self, dt):
        """Return the week that contains the day dt.

        Returns a list of CalendarDay objects.
        """
        start = week_start(dt, self.first_day_of_week)
        end = start + timedelta(7)
        return self.getDays(start, end)

    def getMonth(self, dt):
        """Return a nested list of days in the month that contains dt.

        Returns a list of lists of date objects.  Days in neighbouring
        months are included if they fall into a week that contains days in
        the current month.
        """
        weeks = []
        start_of_next_month = next_month(dt)
        start_of_week = week_start(dt.replace(day=1), self.first_day_of_week)
        while start_of_week < start_of_next_month:
            start_of_next_week = start_of_week + timedelta(7)
            weeks.append(self.getDays(start_of_week, start_of_next_week))
            start_of_week = start_of_next_week
        return weeks

    def getYear(self, dt):
        """Return the current year.

        This returns a list of quarters, each quarter is a list of months,
        each month is a list of weeks, and each week is a list of CalendarDays.
        """
        quarters = []
        for q in range(4):
            quarter = [self.getMonth(date(dt.year, month + (q * 3), 1))
                       for month in range(1, 4)]
            quarters.append(quarter)
        return quarters

    def dayEvents(self, date):
        """Return events for a day sorted by start time.

        Events spanning several days and overlapping with this day
        are included.
        """
        day = self.getDays(date, date + timedelta(1))[0]
        return day.events

    def _eventView(self, event):
        return CalendarEventView(event, self.request, calendar=self.context)

    def eventClass(self, event):
        return self._eventView(event).cssClass()

    def renderEvent(self, event, date):
        return self._eventView(event).full(self.request, date)

    def eventShort(self, event):
        return self._eventView(event).short(self.request)

    def eventHidden(self, event):
        return False # TODO We don't have hidden events yet.

    def eventColors(self, event):
        return ('#9db8d2', '#7590ae') # XXX TODO

    def getDays(self, start, end):
        """Get a list of CalendarDay objects for a selected period of time.

        `start` and `end` (date objects) are bounds (half-open) for the result.

        Events spanning more than one day get included in all days they
        overlap.
        """
        events = {}
        day = start
        while day < end:
            events[day] = []
            day += timedelta(1)

        # We have date objects, but ICalendar.expand needs datetime objects
        start_dt = datetime.combine(start, time())
        end_dt = datetime.combine(end, time())
        for event in self.context.expand(start_dt, end_dt):
            if self.eventHidden(event):
                continue
            #  day1  day2  day3  day4  day5
            # |.....|.....|.....|.....|.....|
            # |     |  [-- event --)  |     |
            # |     |  ^  |     |  ^  |     |
            # |     |  `dtstart |  `dtend   |
            #        ^^^^^       ^^^^^
            #      first_day   last_day
            #
            # dtstart and dtend are datetime.datetime instances and point to
            # time instants.  first_day and last_day are datetime.date
            # instances and point to whole days.  Also note that [dtstart,
            # dtend) is a half-open interval, therefore
            #   last_day == dtend.date() - 1 day   when dtend.time() is 00:00
            #                                      and duration > 0
            #               dtend.date()           otherwise
            dtend = event.dtstart + event.duration
            first_day = event.dtstart.date()
            last_day = max(first_day, (dtend - dtend.resolution).date())
            # Loop through the intersection of two day ranges:
            #    [start, end) intersect [first_day, last_day]
            # Note that the first interval is half-open, but the second one is
            # closed.  Since we're dealing with whole days,
            #    [first_day, last_day] == [first_day, last_day + 1 day)
            day = max(start, first_day)
            limit = min(end, last_day + timedelta(1))
            while day < limit:
                events[day].append(event)
                day += timedelta(1)

        days = []
        day = start
        while day < end:
            events[day].sort()
            days.append(CalendarDay(day, events[day]))
            day += timedelta(1)
        return days

    def prevMonth(self):
        """Return the first day of the previous month."""
        return prev_month(self.cursor)

    def nextMonth(self):
        """Return the first day of the next month."""
        return next_month(self.cursor)

    def prevDay(self):
        return self.cursor - timedelta(1)

    def nextDay(self):
        return self.cursor + timedelta(1)

    def getJumpToYears(self):
        """Return jump targets for five years centered on the current year."""
        this_year = datetime.today().year
        return [{'label': year, 'value': year}
                for year in range(this_year - 2, this_year + 3)]

    def getJumpToMonths(self):
        """Return a list of months for the drop down in the jump portlet."""
        months = []
        for k, v in self.month_names.items():
            months.append({'label': unicode(v), 'value': k})
        return months

    def monthTitle(self, date):
        return unicode(self.month_names[date.month])

    def renderRow(self, week, month):
        """Do some HTML rendering in Python for performance.

        This gains us 0.4 seconds out of 0.6 on my machine.
        Here is the original piece of ZPT:

         <td class="cal_yearly_day" tal:repeat="day week">
          <a tal:condition="python:day.date.month == month[1][0].date.month"
             tal:content="day/date/day"
             tal:attributes="href python:view.calURL('daily', day.date);
                             class python:(len(day.events) > 0
                                           and 'cal_yearly_day_busy'
                                           or  'cal_yearly_day')"/>
         </td>
        """
        result = []

        for day in week:
            result.append('<td class="cal_yearly_day">')
            if day.date.month == month:
                if len(day.events):
                    cssClass = 'cal_yearly_day_busy'
                else:
                    cssClass = 'cal_yearly_day'
                # Let us hope that URLs will not contain < > & or "
                # This is somewhat related to
                #   http://issues.schooltool.org/issue96
                result.append('<a href="%s" class="%s">%s</a>' %
                              (self.calURL('daily', day.date), cssClass,
                               day.date.day))
            result.append('</td>')
        return "\n".join(result)


class WeeklyCalendarView(CalendarViewBase):
    """A view that shows one week of the calendar."""

    __used_for__ = ICalendar

    next_title = _("Next week")
    current_title = _("Current week")
    prev_title = _("Previous week")

    def title(self):
        month_name = unicode(self.month_names[self.cursor.month])
        args = {'month': month_name,
                'year': self.cursor.year,
                'week': self.cursor.isocalendar()[1]}
        return _('%(month)s, %(year)s (week %(week)s)') % args

    def prev(self):
        """Return the link for the previous week."""
        return self.calURL('weekly', self.cursor - timedelta(weeks=1))

    def current(self):
        """Return the link for the current week."""
        return self.calURL('weekly', date.today())

    def next(self):
        """Return the link for the next week."""
        return self.calURL('weekly', self.cursor + timedelta(weeks=1))

    def getCurrentWeek(self):
        """Return the current week as a list of CalendarDay objects."""
        return self.getWeek(self.cursor)


class MonthlyCalendarView(CalendarViewBase):
    """Monthly calendar view."""

    next_title = _("Next month")
    current_title = _("Current month")
    prev_title = _("Previous month")

    def title(self):
        month_name = unicode(self.month_names[self.cursor.month])
        args = {'month': month_name, 'year': self.cursor.year}
        return _('%(month)s, %(year)s') % args

    def prev(self):
        """Return the link for the previous month."""
        return self.calURL('monthly', self.prevMonth())

    def current(self):
        """Return the link for the current month."""
        return self.calURL('monthly', date.today())

    def next(self):
        """Return the link for the next month."""
        return self.calURL('monthly', self.nextMonth())

    def dayOfWeek(self, date):
        return unicode(self.day_of_week_names[date.weekday()])

    def weekTitle(self, date):
        return _('Week %d') % date.isocalendar()[1]

    def getCurrentMonth(self):
        """Return the current month as a nested list of CalendarDays."""
        return self.getMonth(self.cursor)


class YearlyCalendarView(CalendarViewBase):
    """Yearly calendar view."""

    next_title = _("Next year")
    current_title = _("Current year")
    prev_title = _("Previous year")

    def title(self):
        return self.cursor.strftime('%Y')

    def prev(self):
        """Return the link for the previous year."""
        return self.calURL('yearly', date(self.cursor.year - 1, 1, 1))

    def current(self):
        """Return the link for the current year."""
        return self.calURL('yearly', date.today())

    def next(self):
        """Return the link for the next year."""
        return self.calURL('yearly', date(self.cursor.year + 1, 1, 1))

    def shortDayOfWeek(self, date):
        return unicode(self.short_day_of_week_names[date.weekday()])


class CalendarEventView(object):
    """Renders the inside of the event box in various calendar views."""

    # Note: this view is *not* rendered for events in the daily view.

    __used_for__ = ICalendarEvent

    template = ViewPageTemplateFile('templates/cal_event.pt')

    def __init__(self, event, request, calendar=None):
        """Create a view for event.

        Since ordinary calendar events do not know which calendar they come
        from, we have to explicitly provide the access control list (acl)
        that governs access to this calendar.
        """
        self.context = event
        self.request = request
        self.calendar = calendar
        self.date = None

    def canEdit(self):
        """Can the current user edit this calendar event?"""
        return True # TODO: implement this when we have security.

    def canView(self):
        """Can the current user view this calendar event?"""
        return True # TODO: implement this when we have security.

    def isHidden(self):
        """Should the event be hidden from the current user?"""
        return False # TODO

    def cssClass(self):
        """Choose a CSS class for the event."""
        return 'event' # TODO: for now we do not have any other CSS classes.

    def getPeriod(self):
        """Returns the title of the timetable period this event coincides with.

        Returns None if there is no such period.
        """
        return None # XXX Does not apply to SchoolBell.

    def duration(self):
        """Format the time span of the event."""
        dtstart = self.context.dtstart
        dtend = dtstart + self.context.duration
        if dtstart.date() == dtend.date():
            span =  "%s&ndash;%s" % (dtstart.strftime('%H:%M'),
                                     dtend.strftime('%H:%M'))
        else:
            span = "%s&ndash;%s" % (dtstart.strftime('%Y-%m-%d %H:%M'),
                                    dtend.strftime('%Y-%m-%d %H:%M'))

        period = self.getPeriod()
        if period:
            return "Period %s (%s)" % (period, span)
        else:
            return span

    def full(self, request, date):
        """Full representation of the event for daily/weekly views."""
        try:
            self.request = request
            self.date = date
            return self.template(request)
        finally:
            self.request = None
            self.date = None

    def short(self, request):
        """Short representation of the event for the monthly view."""
        self.request = request
        ev = self.context
        end = ev.dtstart + ev.duration
        if self.canView():
            title = ev.title
        else:
            title = _("Busy")
        if ev.dtstart.date() == end.date():
            period = self.getPeriod()
            if period:
                duration = _("Period %s") % period
            else:
                duration =  "%s&ndash;%s" % (ev.dtstart.strftime('%H:%M'),
                                             end.strftime('%H:%M'))
        else:
            duration =  "%s&ndash;%s" % (ev.dtstart.strftime('%b&nbsp;%d'),
                                         end.strftime('%b&nbsp;%d'))
        return "%s (%s)" % (title, duration)

    def editLink(self):
        """Return the link for editing this event."""
        return 'edit_event.html?' + self._params()

    def deleteLink(self):
        """Return the link for deleting this event."""
        # XXX TODO: not used any more
        return 'delete_event.html?' + self._params()

    def _params(self):
        """Prepare query arguments for editLink and deleteLink."""
        event_id = self.context.unique_id
        date = self.date.strftime('%Y-%m-%d')
        return 'date=%s&event_id=%s' % (date, urllib.quote(event_id))

    def privacy(self):
        return _("Public") # TODO used to also have busy-block and hidden.


class DailyCalendarView(CalendarViewBase):
    """Daily calendar view.

    The events are presented as boxes on a 'sheet' with rows
    representing hours.

    The challenge here is to present the events as a table, so that
    the overlapping events are displayed side by side, and the size of
    the boxes illustrate the duration of the events.
    """

    __used_for__ = ICalendar

    starthour = 8
    endhour = 19

    next_title = _("The next day")
    current_title = _("Today")
    prev_title = _("The previous day")

    def title(self):
        return self.dayTitle(self.cursor)

    def prev(self):
        """Return the link for the next day."""
        return self.calURL('daily', self.cursor - timedelta(1))

    def current(self):
        """Return the link for today."""
        return self.calURL('daily', date.today())

    def next(self):
        """Return the link for the previous day."""
        return self.calURL('daily', self.cursor + timedelta(1))

    def getColumns(self):
        """Return the maximum number of events that are overlapping.

        Extends the event so that start and end times fall on hour
        boundaries before calculating overlaps.
        """
        width = [0] * 24
        daystart = datetime.combine(self.cursor, time())
        for event in self.dayEvents(self.cursor):
            t = daystart
            dtend = daystart + timedelta(1)
            for title, start, duration in self.calendarRows():
                if start <= event.dtstart < start + duration:
                    t = start
                if start < event.dtstart + event.duration <= start + duration:
                    dtend = start + duration
            while True:
                width[t.hour] += 1
                t += timedelta(hours=1)
                if t >= dtend:
                    break
        return max(width) or 1

    def _setRange(self, events):
        """Set the starthour and endhour attributes according to events.

        The range of the hours to display is the union of the range
        8:00-18:00 and time spans of all the events in the events
        list.
        """
        for event in events:
            start = datetime.combine(self.cursor, time(self.starthour))
            end = (datetime.combine(self.cursor, time()) +
                   timedelta(hours=self.endhour)) # endhour may be 24
            if event.dtstart < start:
                newstart = max(datetime.combine(self.cursor, time()),
                               event.dtstart)
                self.starthour = newstart.hour

            if event.dtstart + event.duration > end:
                newend = min(
                    datetime.combine(self.cursor, time()) + timedelta(1),
                    event.dtstart + event.duration + timedelta(0, 3599))
                self.endhour = newend.hour
                if self.endhour == 0:
                    self.endhour = 24

    def calendarRows(self):
        """Iterate over (title, start, duration) of time slots that make up
        the daily calendar.
        """
        # XXX not tested
        today = datetime.combine(self.cursor, time())
        row_ends = [today + timedelta(hours=hour + 1)
                    for hour in range(self.starthour, self.endhour)]

        start = today + timedelta(hours=self.starthour)
        for end in row_ends:
            duration = end - start
            yield ('%d:%02d' % (start.hour, start.minute), start, duration)
            start = end

    def getHours(self):
        """Return an iterator over the rows of the table.

        Every row is a dict with the following keys:

            'time' -- row label (e.g. 8:00)
            'cols' -- sequence of cell values for this row

        A cell value can be one of the following:
            None  -- if there is no event in this cell
            event -- if an event starts in this cell
            ''    -- if an event started above this cell

        """
        nr_cols = self.getColumns()
        events = self.dayEvents(self.cursor)
        self._setRange(events)
        slots = Slots()
        for title, start, duration in self.calendarRows():
            end = start + duration
            hour = start.hour

            # Remove the events that have already ended
            for i in range(nr_cols):
                ev = slots.get(i, None)
                if ev is not None and ev.dtstart + ev.duration <= start:
                    del slots[i]

            # Add events that start during (or before) this hour
            while (events and events[0].dtstart < end):
                event = events.pop(0)
                slots.add(event)

            cols = []
            # Format the row
            for i in range(nr_cols):
                ev = slots.get(i, None)
                if (ev is not None
                    and ev.dtstart < start
                    and hour != self.starthour):
                    # The event started before this hour (except first row)
                    cols.append('')
                else:
                    # Either None, or new event
                    cols.append(ev)

            yield {'title': title, 'cols': tuple(cols),
                   'time': start.strftime("%H:%M"),
                   # We can trust no period will be longer than a day
                   'duration': duration.seconds // 60}

    def rowspan(self, event):
        """Calculate how many calendar rows the event will take today."""
        count = 0
        for title, start, duration in self.calendarRows():
            if (start < event.dtstart + event.duration and
                event.dtstart < start + duration):
                count += 1
        return count

    def snapToGrid(self, dt):
        """Snap a datetime to the nearest position in the grid.

        Returns the grid line index where 0 corresponds to the top of
        the display box (self.starthour), and each subsequent line represents
        a 15 minute increment.

        Clips dt so that it is never outside today's box.
        """
        base = datetime.combine(self.cursor, time())
        display_start = base + timedelta(hours=self.starthour)
        display_end = base + timedelta(hours=self.endhour)
        clipped_dt = max(display_start, min(dt, display_end))
        td = clipped_dt - display_start
        offset_in_minutes = td.seconds / 60 + td.days * 24 * 60
        return (offset_in_minutes + 7) / 15 # round to nearest quarter

    def eventTop(self, event):
        """Calculate the position of the top of the event block in the display.

        Each hour is made up of 4 units ('em' currently). If an event starts at
        10:15, and the day starts at 8:00 we get a top value of:

          (2 * 4) + (15 / 15) = 9

        """
        return self.snapToGrid(event.dtstart)

    def eventHeight(self, event):
        """Calculate the height of the event block in the display.

        Each hour is made up of 4 units ('em' currently).  Need to round 1 -
        14 minute intervals up to 1 display unit.
        """
        dtend = event.dtstart + event.duration
        return max(1, self.snapToGrid(dtend) - self.snapToGrid(event.dtstart))

    def update(self):
        # Create self.cursor
        CalendarViewBase.update(self)

        # Initialize self.starthour and self.endhour
        events = self.dayEvents(self.cursor)
        self._setRange(events)

        # The number of hours displayed in the day view
        self.visiblehours = self.endhour - self.starthour


class EventDeleteView(BrowserView):
    """A view for deleting events."""

    __used_for__ = ICalendar

    def __call__(self):
        event_id = self.request['event_id']
        try:
            event = self.context.find(event_id)
        except KeyError:
            pass # Somebody else did the job for us, how nice of them.
        else:
            self.context.removeEvent(event)

        isodate = self.request['date']
        url = '%s/%s' % (absoluteURL(self.context, self.request), isodate)
        self.request.response.redirect(url)


class Slots(dict):
    """A dict with automatic key selection.

    The add method automatically selects the lowest unused numeric key
    (starting from 0).

    Example:

      >>> s = Slots()
      >>> s.add("first")
      >>> s
      {0: 'first'}

      >>> s.add("second")
      >>> s
      {0: 'first', 1: 'second'}

    The keys can be reused:

      >>> del s[0]
      >>> s.add("third")
      >>> s
      {0: 'third', 1: 'second'}

    """

    def add(self, obj):
        i = 0
        while i in self:
            i += 1
        self[i] = obj


def vocabulary(choices):
    """Create a SimpleVocabulary from a list of values and titles.

    >>> v = vocabulary([('value1', u"Title for value1"),
    ...                 ('value2', u"Title for value2")])
    >>> for term in v:
    ...   print term.value, '|', term.token, '|', term.title
    value1 | value1 | Title for value1
    value2 | value2 | Title for value2

    """
    return SimpleVocabulary([SimpleTerm(v, title=t) for v, t in choices])


class ICalendarEventAddForm(Interface):
    """Schema for event adding form."""

    title = TextLine(
        title=_("Title"),
        required=False)
    start_date = Date(
        title=_("Date"),
        required=False)
    start_time = TextLine(
        title=_("Time"),
        required=False)

    duration = Int(
        title=_("Duration"),
        required=False,
        default=60)

    location = TextLine(
        title=_("Location"),
        required=False)

    # Recurrence
    recurrence = Bool(
        title=_("Recurring"),
        required=False)

    recurrence_type = Choice(
        title=_("Recurs every"),
        required=True,
        default="daily",
        vocabulary=vocabulary([("daily", _("Day")),
                               ("weekly", _("Week")),
                               ("monthly", _("Month")),
                               ("yearly", _("Year"))]))

    interval = Int(
        title=u"Repeat every",
        required=False,
        default=1)

    range = Choice(
        title=_("Range"),
        required=False,
        default="forever",
        vocabulary=vocabulary([("count", _("Count")),
                               ("until", _("Until")),
                               ("forever", _("forever"))]))

    count = Int(
        title=_("Number of events"),
        required=False)

    until = Date(
        title=_("Repeat until"),
        required=False)

    weekdays = List(
        title=_("Weekdays"),
        required=False,
        value_type=Choice(
            title=_("Weekday"),
            vocabulary=vocabulary([("0", _("Mon")),
                                   ("1", _("Tue")),
                                   ("2", _("Wed")),
                                   ("3", _("Thu")),
                                   ("4", _("Fri")),
                                   ("5", _("Sat")),
                                   ("6", _("Sun"))])))

    monthly = Choice(
        title=_("Monthly"),
        default="monthday",
        required=False,
        vocabulary=vocabulary([("monthday", "md"),
                               ("weekday", "wd"),
                               ("lastweekday", "lwd")]))

    exceptions = Text(
        title=_("Exception dates"),
        required=False)


class CalendarEventAddView(AddView):
    """A view for adding an event."""

    __used_for__ = ICalendar
    schema = ICalendarEventAddForm

    error = None

    def _setError(self, name, error=RequiredMissing()):
        """Set an error on a widget."""
        # XXX Touching widget._error is bad, see
        #     http://dev.zope.org/Zope3/AccessToWidgetErrors
        # The call to setRenderedValue is necessary because
        # otherwise _getFormValue will call getInputValue and
        # overwrite _error while rendering.
        widget = getattr(self, name + '_widget')
        widget.setRenderedValue(widget._getFormValue())
        if not IWidgetInputError.providedBy(error):
            error = WidgetInputError(name, widget.label, error)
        widget._error = error

    def _requireField(self, name, errors):
        """If widget has no input, WidgetInputError is set.

        Also adds the exception to the `errors` list.
        """
        widget = getattr(self, name + '_widget')
        field = widget.context
        try:
            if widget.getInputValue() == field.missing_value:
                self._setError(name)
                errors.append(widget._error)
        except WidgetInputError, e:
            # getInputValue might raise an exception on invalid input
            errors.append(e)

    def create(self, **kwargs):
        """Create an event.

        This method performs additional validation, because Zope 3 forms aren't
        powerful enough.  If any errors are encountered, raises a WidgetsError.
        """
        errors = []
        self._requireField("title", errors)
        self._requireField("start_date", errors)
        self._requireField("start_time", errors)
        self._requireField("duration", errors)

        # Remove fields not needed for makeRecurrenceRule from kwargs
        title = kwargs.pop('title', None)
        start_date = kwargs.pop('start_date', None)
        start_time = kwargs.pop('start_time', None)
        if start_time:
            try:
                start_time = parse_time(start_time)
            except ValueError:
                self._setError("start_time", ConversionError(_(
                            "Invalid time")))
                errors.append(self.start_time_widget._error)
        duration = kwargs.pop('duration', None)
        location = kwargs.pop('location', None)
        recurrence = kwargs.pop('recurrence', None)

        if recurrence:
            self._requireField("interval", errors)
            self._requireField("recurrence_type", errors)
            self._requireField("range", errors)

            range = kwargs.get('range')
            if range == "count":
                self._requireField("count", errors)
            elif range == "until":
                self._requireField("until", errors)
                if start_date and kwargs.get('until'):
                    if kwargs['until'] < start_date:
                        self._setError("until", ConstraintNotSatisfied(_(
                                    "End date is earlier than start date")))
                        errors.append(self.until_widget._error)

        exceptions = kwargs.pop("exceptions", None)
        if exceptions:
            try:
                kwargs["exceptions"] = datesParser(exceptions)
            except:
                self._setError("exceptions", ConversionError(_(
                    "Invalid date.  Please specify YYYY-MM-DD, one per line.")))
                errors.append(self.exceptions_widget._error)

        if errors:
            raise WidgetsError(errors)

        start = datetime.combine(start_date, start_time)
        duration = timedelta(minutes=duration)

        rrule = recurrence and makeRecurrenceRule(**kwargs) or None
        event = self._factory(start, duration, title,
                              recurrence=rrule, location=location)
        return event

    def add(self, event):
        """Add the event to a calendar."""
        self.context.addEvent(event)
        return event

    def update(self):
        """Process the form."""
        if 'UPDATE' in self.request:
            # Just refresh the form.  It is necessary because some labels for
            # monthly recurrence rules depend on the event start date.
            self.update_status = ''
            try:
                data = getWidgetsData(self, self.schema, names=self.fieldNames)
                args = [data[name] for name in self._arguments]
                kw = {}
                for name in self._keyword_arguments:
                    if name in data:
                        kw[str(name)] = data[name]
                self.create(*args, **kw)
            except WidgetsError, errors:
                self.errors = errors
                self.update_status = _("An error occured.")
                return self.update_status
            # AddView.update() sets self.update_status and returns it.  Weird,
            # but let's copy that behavior.
            return self.update_status
        else:
            return AddView.update(self)

    def nextURL(self):
        """Return the URL to be displayed after the add operation."""
        return absoluteURL(self.context, self.request)

    def getMonthDay(self):
        """Return the day number in a month, according to start_date.

        Used by the page template to format monthly recurrence rules.
        """
        try:
            evdate = self.start_date_widget.getInputValue()
        except WidgetInputError:
            evdate = None
        if evdate is None:
            return '??'
        else:
            return str(evdate.day)

    def getWeekDay(self):
        """Return the week and weekday in a month, according to start_date.

        The output looks like '4th Tuesday'

        Used by the page template to format monthly recurrence rules.
        """
        try:
            evdate = self.start_date_widget.getInputValue()
        except WidgetInputError:
            evdate = None
        if evdate is None:
            return _("same weekday")

        weekday = evdate.weekday()
        index = (evdate.day + 6) // 7

        indexes = {1: _('1st'), 2: _('2nd'), 3: _('3rd'), 4: _('4th'),
                   5: _('5th')}
        day_of_week = CalendarViewBase.day_of_week_names[weekday]
        return "%s %s" % (indexes[index], day_of_week)

    def getLastWeekDay(self):
        """Return the week and weekday in a month, counting from the end.

        The output looks like 'Last Friday'

        Used by the page template to format monthly recurrence rules.
        """
        try:
            evdate = self.start_date_widget.getInputValue()
        except WidgetInputError:
            evdate = None

        if evdate is None:
            return _("last weekday")

        lastday = calendar.monthrange(evdate.year, evdate.month)[1]

        if lastday - evdate.day >= 7:
            return None
        else:
            weekday = evdate.weekday()
            day_of_week = unicode(CalendarViewBase.day_of_week_names[weekday])
            return _("Last %(weekday)s") % {'weekday': day_of_week}

    def weekdayChecked(self, weekday):
        """Return True if the given weekday should be checked.

        The weekday of start_date is always checked, others can be selected by
        the user.

        Used to format checkboxes for weekly recurrences.
        """
        return (weekday in self.weekdays_widget._getFormValue() or
                self.weekdayDisabled(weekday))

    def weekdayDisabled(self, weekday):
        """Return True if the given weekday should be disabled.

        The weekday of start_date is always disabled, all others are always
        enabled.

        Used to format checkboxes for weekly recurrences.
        """
        try:
            day = self.start_date_widget.getInputValue()
        except WidgetInputError:
            day = None
        return bool(day and str(day.weekday()) == weekday)


def makeRecurrenceRule(interval=None, until=None,
                       count=None, range=None,
                       exceptions=None, recurrence_type=None,
                       weekdays=None, monthly=None):
    """Return a recurrence rule according to the arguments."""
    if interval is None:
        interval = 1

    if range != 'until':
        until = None
    if range != 'count':
        count = None

    if exceptions is None:
        exceptions = ()

    kwargs = {'interval': interval, 'count': count,
              'until': until, 'exceptions': exceptions}

    if recurrence_type == 'daily':
        return DailyRecurrenceRule(**kwargs)
    elif recurrence_type == 'weekly':
        weekdays = weekdays or ()
        return WeeklyRecurrenceRule(weekdays=tuple(weekdays), **kwargs)
    elif recurrence_type == 'monthly':
        monthly = monthly or "monthday"
        return MonthlyRecurrenceRule(monthly=monthly, **kwargs)
    elif recurrence_type == 'yearly':
        return YearlyRecurrenceRule(**kwargs)
    else:
        raise NotImplementedError()


def datesParser(raw_dates):
    r"""Parse dates on separate lines into a tuple of date objects.

    Incorrect lines are ignored.

    >>> datesParser('2004-05-17\n\n\n2004-01-29')
    (datetime.date(2004, 5, 17), datetime.date(2004, 1, 29))

    >>> datesParser('2004-05-17\n123\n\nNone\n2004-01-29')
    Traceback (most recent call last):
    ...
    ValueError: Invalid date: '123'

    """
    results = []
    for dstr in raw_dates.splitlines():
        if dstr:
            d = parse_date(dstr)
            if isinstance(d, date):
                results.append(d)
    return tuple(results)
