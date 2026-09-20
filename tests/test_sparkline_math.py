"""The polyline maths behind the sparklines and the chart.

Pure geometry, so it's testable without a Qt event loop — which is where
off-by-one and inverted-axis mistakes actually show up.
"""

import pytest

from netwatch.ui.sparkline import (
    MIN_CEILING,
    area_path,
    ceiling_for,
    line_path,
    normalise,
    points,
)


def test_empty_series_normalises_to_nothing():
    assert normalise([]) == []


def test_all_zero_series_is_flat_at_the_bottom():
    assert normalise([0, 0, 0]) == [0.0, 0.0, 0.0]


def test_series_is_scaled_against_an_explicit_ceiling():
    assert normalise([0, 5, 10], ceiling=10) == [0.0, 0.5, 1.0]


def test_a_steady_series_leaves_headroom_above_the_line():
    """Most processes hold a constant connection count. Scaling to the peak
    alone would pin the line to the top and flood the fill."""
    for value in normalise([7, 7, 7]):
        assert value < 1.0


def test_small_counts_do_not_look_maxed_out():
    assert normalise([1])[0] <= 1 / MIN_CEILING


def test_ceiling_has_headroom_above_the_peak():
    assert ceiling_for([100]) > 100


def test_ceiling_has_a_floor_for_tiny_series():
    assert ceiling_for([1]) == MIN_CEILING
    assert ceiling_for([]) == MIN_CEILING


def test_values_above_the_ceiling_are_clamped():
    assert normalise([50], ceiling=10) == [1.0]


def test_points_span_the_full_width():
    pts = points([0.0, 0.5, 1.0], 96.0, 26.0)
    assert pts[0].x() == 0.0
    assert pts[-1].x() == 96.0


def test_y_axis_is_inverted_so_high_values_sit_high():
    pad = 2.0
    height = 26.0
    low, _, high = points([0.0, 0.5, 1.0], 96.0, height, pad)
    assert low.y() == height - pad          # zero sits on the baseline
    assert high.y() == pad                  # peak sits at the top inset
    assert high.y() < low.y()


def test_padding_keeps_the_line_inside_the_box():
    for pt in points([0.0, 1.0], 100.0, 130.0, pad=6.0):
        assert 6.0 <= pt.y() <= 124.0


def test_single_sample_draws_a_flat_line_across():
    pts = points([0.5], 96.0, 26.0)
    assert len(pts) == 2
    assert pts[0].y() == pts[1].y()
    assert (pts[0].x(), pts[1].x()) == (0.0, 96.0)


def test_no_samples_draws_nothing():
    assert points([], 96.0, 26.0) == []
    assert line_path([]).elementCount() == 0


def test_area_path_closes_down_to_the_baseline():
    pts = points([1.0, 1.0], 96.0, 26.0)
    path = area_path(pts, 96.0, 26.0)
    ys = [path.elementAt(i).y for i in range(path.elementCount())]
    assert max(ys) == 26.0, "fill must reach the bottom of the box"


def test_area_path_of_an_empty_series_is_empty():
    assert area_path([], 96.0, 26.0).elementCount() == 0


@pytest.mark.parametrize("count", [2, 5, 24, 30])
def test_points_are_evenly_spaced(count):
    pts = points([0.5] * count, 96.0, 26.0)
    gaps = [round(pts[i + 1].x() - pts[i].x(), 6) for i in range(len(pts) - 1)]
    assert len(set(gaps)) == 1
