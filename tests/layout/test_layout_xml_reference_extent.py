import datetime
import xml.etree.ElementTree as ET

from gopro_overlay.entry import Entry
from gopro_overlay.framemeta import FrameMeta
from gopro_overlay.layout_xml import Widgets, Converters
from gopro_overlay.point import Point
from gopro_overlay.timeunits import timeunits
from gopro_overlay.widgets.chart import JourneyChart, SimpleChart
from gopro_overlay.widgets.map import JourneyMap


def datetime_of(i):
    return datetime.datetime.fromtimestamp(i, tz=datetime.timezone.utc)


def framemeta_over(seconds_range, lat0=1.0):
    fm = FrameMeta()
    for s in seconds_range:
        fm.add(
            timeunits(seconds=s),
            Entry(datetime_of(s), point=Point(lat=lat0 + s, lon=2.0), alt=100 + s),
        )
    return fm


class FakeFont:
    def font_variant(self, size):
        return None


def make_factory(clip, reference):
    return Widgets(
        font=lambda size: None,
        privacy=None,
        renderer=lambda m: None,
        framemeta=clip,
        converters=Converters(),
        reference_framemeta=reference,
    )


def entry_fn():
    return Entry(datetime_of(5), point=Point(lat=6.0, lon=2.0), alt=105,
                 timestamp=None)


def test_reference_framemeta_defaults_to_clip_when_absent():
    clip = framemeta_over(range(3))
    factory = Widgets(
        font=lambda size: None, privacy=None, renderer=lambda m: None,
        framemeta=clip, converters=Converters(),
    )
    assert factory.reference_framemeta is clip


def test_reference_framemeta_used_when_provided():
    clip = framemeta_over(range(3))
    ride = framemeta_over(range(11))
    factory = make_factory(clip, ride)
    assert factory.reference_framemeta is ride


def test_chart_range_window_uses_simple_chart():
    clip = framemeta_over(range(3))
    ride = framemeta_over(range(11))
    factory = make_factory(clip, ride)
    el = ET.fromstring('<component type="chart" metric="alt" />')
    widget = factory.create_chart(el, entry_fn).widget
    assert isinstance(widget, SimpleChart)


def test_chart_range_ride_uses_journey_chart_with_reference():
    clip = framemeta_over(range(3))
    ride = framemeta_over(range(11))
    factory = make_factory(clip, ride)
    el = ET.fromstring('<component type="chart" metric="alt" range="ride" />')
    widget = factory.create_chart(el, entry_fn).widget
    assert isinstance(widget, JourneyChart)
    assert widget.framemeta is ride


def test_journey_map_extent_clip_uses_clip_series():
    clip = framemeta_over(range(3))
    ride = framemeta_over(range(11))
    factory = make_factory(clip, ride)
    el = ET.fromstring('<component type="journey_map" />')
    widget = factory.create_journey_map(el, entry_fn)
    assert isinstance(widget, JourneyMap)
    assert widget.timeseries is clip


def test_journey_map_extent_ride_uses_reference_series():
    clip = framemeta_over(range(3))
    ride = framemeta_over(range(11))
    factory = make_factory(clip, ride)
    el = ET.fromstring('<component type="journey_map" extent="ride" />')
    widget = factory.create_journey_map(el, entry_fn)
    assert isinstance(widget, JourneyMap)
    assert widget.timeseries is ride
