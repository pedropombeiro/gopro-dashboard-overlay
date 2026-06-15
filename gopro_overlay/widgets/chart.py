from PIL import Image, ImageDraw

from .map import draw_marker
from .widgets import Widget


class JourneyChart(Widget):
    """Static chart of a metric across the *whole* journey, with a marker that
    tracks the current position.

    Unlike SimpleChart (which scrolls a fixed-duration window past a centred
    marker), JourneyChart renders the entire ride's profile once and moves the
    marker along it. This gives whole-ride context - e.g. the complete elevation
    profile - regardless of which clip is being rendered.

    The profile and y-scale come from `framemeta` (intended to be the full ride).
    The marker is placed by mapping `location_time_fn()` - the current frame's
    datetime, as POSIX seconds - onto the ride's time span.
    """

    def __init__(
            self,
            framemeta,
            metric,
            location_time_fn,
            font=None,
            filled=False,
            height=64,
            width=256,
            samples=256,
            marker_size=4,
            bg=(0, 0, 0, 170),
            fill=(91, 113, 146),
            line=(255, 255, 255),
            text=(255, 255, 255),
            marker_fill=(255, 0, 0),
    ):
        self.framemeta = framemeta
        self.metric = metric
        self.location_time_fn = location_time_fn
        self.font = font
        self.filled = filled
        self.height = height
        self.width = width
        self.samples = samples
        self.marker_size = marker_size
        self.bg = bg
        self.fill = fill
        self.line = line
        self.text = text
        self.marker_fill = marker_fill

        self.chart_image = None  # cached profile body (no marker)
        self._data = None        # list of (sample_value | None) across the ride
        self._min_val = 0.0
        self._scale_y = 1.0
        self._t_start = None     # ride start, POSIX seconds
        self._t_end = None       # ride end, POSIX seconds

    def _y_pos(self, val):
        return self.height - 1 - (val - self._min_val) * self._scale_y

    def _x_pos(self, idx):
        if self.samples <= 1:
            return 0
        return idx * (self.width / (self.samples - 1))

    def _init_maybe(self):
        if self.chart_image is not None:
            return

        start = self.framemeta.min
        end = self.framemeta.max
        self._t_start = self.framemeta.date_at(start).timestamp()
        self._t_end = self.framemeta.date_at(end).timestamp()

        span = end - start
        # Sample the ride at `samples` evenly spaced points across its duration.
        data = []
        for i in range(self.samples):
            frac = i / (self.samples - 1) if self.samples > 1 else 0.0
            at = start + (span * frac)
            entry = self.framemeta.get(at)
            value = self.metric(entry)
            data.append(value)

        self._data = data

        values = [v for v in data if v is not None]
        max_val = max(values, default=0)
        min_val = min(values, default=0)
        range_val = max(max_val - min_val, 1)

        self._min_val = min_val
        self._scale_y = self.height / (range_val * 1.1)

        self.chart_image = Image.new("RGBA", (self.width, self.height), self.bg)
        chart_draw = ImageDraw.Draw(self.chart_image)

        points = [(self._x_pos(i), self._y_pos(v)) for i, v in enumerate(data) if v is not None]

        if self.filled and len(points) >= 2:
            baseline = self.height - 1
            poly = points + [(points[-1][0], baseline), (points[0][0], baseline)]
            chart_draw.polygon(poly, fill=self.fill)

        if len(points) >= 2:
            chart_draw.line(points, width=2, fill=self.line)

        if self.font:
            chart_draw.text((10, 4), f"{max_val:.0f}", font=self.font, fill=self.text,
                            stroke_width=2, stroke_fill=(0, 0, 0), anchor="lt")
            chart_draw.text((10, self.height - 10), f"{min_val:.0f}", font=self.font,
                            fill=self.text, stroke_width=2, stroke_fill=(0, 0, 0), anchor="lb")

    def _marker_index(self):
        now = self.location_time_fn()
        if now is None or self._t_end is None or self._t_end <= self._t_start:
            return 0.0
        frac = (now - self._t_start) / (self._t_end - self._t_start)
        frac = max(0.0, min(1.0, frac))
        return frac * (self.samples - 1)

    def draw(self, image: Image, draw: ImageDraw):
        self._init_maybe()

        image.alpha_composite(self.chart_image, (0, 0))

        if not self._data:
            return

        frac_idx = self._marker_index()
        lo = int(frac_idx)
        hi = min(lo + 1, self.samples - 1)
        t = frac_idx - lo

        if 0 <= lo < self.samples and self._data[lo] is not None and self._data[hi] is not None:
            y_val = self._data[lo] * (1 - t) + self._data[hi] * t
        elif 0 <= lo < self.samples and self._data[lo] is not None:
            y_val = self._data[lo]
        else:
            y_val = None

        if y_val is not None:
            draw_marker(draw, (self._x_pos(frac_idx), self._y_pos(y_val)),
                        self.marker_size, fill=self.marker_fill)


class SimpleChart(Widget):

    def __init__(
            self,
            value,
            font=None,
            filled=False,
            height=64,
            width=None,
            marker_time_fn=None,
            window_tick_ms=100,
            marker_size=4,
            bg=(0, 0, 0, 170),
            fill=(91, 113, 146),
            line=(255, 255, 255),
            text=(255, 255, 255),
    ):
        self.value = value
        self.filled = filled
        self.font = font
        self.height = height
        self.width = width
        self.marker_time_fn = marker_time_fn
        self.window_tick_ms = window_tick_ms
        self.marker_size = marker_size
        self.fill = fill
        self.bg = bg
        self.line = line
        self.text = text

        self.view = None
        self.chart_image = None  # cached body without marker

        # state preserved between frames for smooth marker interpolation
        self._data = None
        self._n = 0
        self._x_first = 0
        self._x_last = 0
        self._x_scale = 1.0
        self._min_val = 0
        self._scale_y = 1.0

    # ------------------------------------------------------------------
    # helpers (use stored state so they work outside the cache block)
    # ------------------------------------------------------------------

    def _x_pos(self, idx):
        return (idx - self._x_first) * self._x_scale

    def _y_pos(self, val):
        return self.height - 1 - (val - self._min_val) * self._scale_y

    # ------------------------------------------------------------------

    def draw(self, image: Image, draw: ImageDraw):
        view = self.value()

        if not (self.view and self.view.version == view.version):
            self.view = view
            data = view.data
            n = len(data)
            render_width = self.width if self.width is not None else n
            size = (render_width, self.height)
            self.chart_image = Image.new("RGBA", size, self.bg)
            chart_draw = ImageDraw.Draw(self.chart_image)

            values = [v for v in data if v is not None]
            max_val = max(values, default=0)
            min_val = min(values, default=0)
            range_val = max(max_val - min_val, 1)

            # store state needed for per-frame marker drawing
            self._data = data
            self._n = n
            self._min_val = min_val
            self._scale_y = size[1] / (range_val * 1.1)

            filtered = [(i, y) for i, y in enumerate(data) if y is not None]

            if self.width is not None and filtered:
                self._x_first = filtered[0][0]
                self._x_last = filtered[-1][0]
                self._x_scale = render_width / max(self._x_last - self._x_first, 1)
            else:
                self._x_first = 0
                self._x_last = n - 1
                self._x_scale = render_width / n if n > 0 else 1

            points = [(self._x_pos(i), self._y_pos(y)) for i, y in filtered]

            if self.filled and len(points) >= 2:
                baseline = size[1] - 1
                poly = points + [(points[-1][0], baseline), (points[0][0], baseline)]
                chart_draw.polygon(poly, fill=self.fill)

            if len(points) >= 2:
                chart_draw.line(points, width=2, fill=self.line)

            if self.font:
                chart_draw.text((10, 4), f"{max_val:.0f}", font=self.font, fill=self.text,
                                stroke_width=2, stroke_fill=(0, 0, 0), anchor="lt")
                chart_draw.text((10, self.height - 10), f"{min_val:.0f}", font=self.font,
                                fill=self.text, stroke_width=2, stroke_fill=(0, 0, 0), anchor="lb")

        # composite cached chart body
        image.alpha_composite(self.chart_image, (0, 0))

        # draw marker every frame with sub-tick interpolation for smooth movement
        if self._data is not None:
            if self.marker_time_fn is not None:
                raw_ms = self.marker_time_fn()
                frac = (raw_ms % self.window_tick_ms) / self.window_tick_ms
                marker_frac_idx = self._n // 2 + frac
            else:
                marker_frac_idx = float(self._n // 2)

            # clamp to the actual data range so the marker never escapes the chart
            marker_frac_idx = max(float(self._x_first), min(float(self._x_last), marker_frac_idx))

            lo = int(marker_frac_idx)
            hi = min(lo + 1, self._x_last)
            t = marker_frac_idx - lo
            data = self._data

            if 0 <= lo < self._n and 0 <= hi < self._n \
                    and data[lo] is not None and data[hi] is not None:
                y_val = data[lo] * (1 - t) + data[hi] * t
            elif 0 <= lo < self._n and data[lo] is not None:
                y_val = data[lo]
            elif 0 <= hi < self._n and data[hi] is not None:
                y_val = data[hi]
            else:
                y_val = None

            if y_val is not None:
                draw_marker(draw, (self._x_pos(marker_frac_idx), self._y_pos(y_val)),
                            self.marker_size, fill=(255, 0, 0))
