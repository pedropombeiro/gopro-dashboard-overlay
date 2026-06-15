import datetime

from PIL import Image

from gopro_overlay.entry import Entry
from gopro_overlay.framemeta import FrameMeta
from gopro_overlay.point import Point
from gopro_overlay.timeunits import timeunits
from gopro_overlay.widgets.chart import JourneyChart


def datetime_of(i):
    return datetime.datetime.fromtimestamp(i, tz=datetime.timezone.utc)


def ride_framemeta():
    """A 10-second ride climbing linearly from 100m to 200m."""
    fm = FrameMeta()
    for second in range(11):
        alt = 100 + second * 10
        fm.add(
            timeunits(seconds=second),
            Entry(datetime_of(second), point=Point(lat=1.0 + second, lon=2.0), alt=alt),
        )
    return fm


def alt_metric(entry):
    return entry.alt if entry.alt is not None else None


def make_chart(framemeta, now_fn, **kwargs):
    return JourneyChart(
        framemeta=framemeta,
        metric=alt_metric,
        location_time_fn=now_fn,
        font=None,
        width=100,
        height=50,
        samples=11,
        **kwargs,
    )


def test_profile_samples_whole_ride():
    chart = make_chart(ride_framemeta(), lambda: datetime_of(0).timestamp())
    chart._init_maybe()
    # samples span the whole ride, not a clip window
    assert chart._data[0] == 100
    assert chart._data[-1] == 200


def test_scale_uses_whole_ride_min_max():
    chart = make_chart(ride_framemeta(), lambda: datetime_of(0).timestamp())
    chart._init_maybe()
    assert chart._min_val == 100
    # scale_y maps the full 100m range across the height (with 1.1 headroom)
    assert chart._scale_y == 50 / (100 * 1.1)


def test_marker_index_at_start():
    chart = make_chart(ride_framemeta(), lambda: datetime_of(0).timestamp())
    chart._init_maybe()
    assert chart._marker_index() == 0.0


def test_marker_index_at_end():
    chart = make_chart(ride_framemeta(), lambda: datetime_of(10).timestamp())
    chart._init_maybe()
    assert chart._marker_index() == float(chart.samples - 1)


def test_marker_index_halfway():
    chart = make_chart(ride_framemeta(), lambda: datetime_of(5).timestamp())
    chart._init_maybe()
    assert chart._marker_index() == (chart.samples - 1) / 2


def test_marker_index_clamped_before_ride():
    # A frame timestamped before the ride start clamps to the first sample.
    chart = make_chart(ride_framemeta(), lambda: datetime_of(-100).timestamp())
    chart._init_maybe()
    assert chart._marker_index() == 0.0


def test_marker_index_clamped_after_ride():
    # A frame timestamped after the ride end clamps to the last sample.
    chart = make_chart(ride_framemeta(), lambda: datetime_of(100).timestamp())
    chart._init_maybe()
    assert chart._marker_index() == float(chart.samples - 1)


def test_marker_tracks_clip_offset_into_full_ride():
    # The marker is driven by absolute datetime, so a clip covering only
    # seconds 5..7 of the ride still positions the marker correctly on the
    # whole-ride profile.
    chart = make_chart(ride_framemeta(), lambda: datetime_of(7).timestamp())
    chart._init_maybe()
    assert chart._marker_index() == 7.0 / 10.0 * (chart.samples - 1)


def test_draw_does_not_raise_and_composites():
    chart = make_chart(ride_framemeta(), lambda: datetime_of(5).timestamp())
    image = Image.new("RGBA", (100, 50), (0, 0, 0, 0))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(image)
    chart.draw(image, draw)
    # something was drawn (non-transparent pixels exist)
    assert image.getbbox() is not None


def test_handles_missing_values_gracefully():
    fm = FrameMeta()
    fm.add(timeunits(seconds=0), Entry(datetime_of(0), point=Point(lat=1.0, lon=2.0), alt=None))
    fm.add(timeunits(seconds=1), Entry(datetime_of(1), point=Point(lat=2.0, lon=2.0), alt=150))
    chart = make_chart(fm, lambda: datetime_of(0).timestamp())
    image = Image.new("RGBA", (100, 50), (0, 0, 0, 0))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(image)
    chart.draw(image, draw)  # must not raise
