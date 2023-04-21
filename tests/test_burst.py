from pathlib import Path

import pytest
from lxml import etree
from shapely import geometry

from hyp3_isce2 import burst


URL_BASE = 'https://datapool.asf.alaska.edu/SLC'
REF_DESC = burst.BurstParams('S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85', 'IW2', 'VV', 3)
SEC_DESC = burst.BurstParams('S1A_IW_SLC__1SDV_20200616T022252_20200616T022319_033036_03D3A3_5D11', 'IW2', 'VV', 3)
REF_ASC = burst.BurstParams('S1A_IW_SLC__1SDV_20211229T231926_20211229T231953_041230_04E66A_3DBE', 'IW1', 'VV', 4)
SEC_ASC = burst.BurstParams('S1A_IW_SLC__1SDV_20220110T231926_20220110T231953_041405_04EC57_103E', 'IW1', 'VV', 4)


def load_metadata(metadata):
    metadata_path = Path(__file__).parent.absolute() / 'data' / metadata
    xml = etree.parse(metadata_path).getroot()
    return xml


@pytest.mark.parametrize(
    'pattern',
    (
        '*SAFE',
        '*SAFE/annotation/*xml',
        '*SAFE/annotation/calibration/calibration*xml',
        '*SAFE/annotation/calibration/noise*xml',
        '*SAFE/measurement/*tiff',
    ),
)
def test_spoof_safe(tmp_path, mocker, pattern):
    mock_tiff = tmp_path / 'test.tiff'
    mock_tiff.touch()

    ref_burst = burst.BurstMetadata(load_metadata('reference_descending.xml'), REF_DESC)
    burst.spoof_safe(ref_burst, mock_tiff, tmp_path)
    assert len(list(tmp_path.glob(pattern))) == 1


@pytest.mark.parametrize('orbit', ('ascending', 'descending'))
def test_get_region_of_interest(orbit):
    options = {'descending': REF_DESC, 'ascending': REF_ASC}

    params = options[orbit]
    ref_metadata = load_metadata(f'reference_{orbit}.xml')
    ref_burst = burst.BurstMetadata(ref_metadata, params)
    sec_burst = burst.BurstMetadata(load_metadata(f'secondary_{orbit}.xml'), params)

    granule = params.granule
    burst_number = params.burst_number
    swath = params.swath
    pol = params.polarization

    burst_pre = burst.BurstMetadata(ref_metadata, burst.BurstParams(granule, swath, pol, burst_number - 1))
    burst_on = burst.BurstMetadata(ref_metadata, burst.BurstParams(granule, swath, pol, burst_number))
    burst_post = burst.BurstMetadata(ref_metadata, burst.BurstParams(granule, swath, pol, burst_number + 1))

    asc = ref_burst.orbit_direction == 'ascending'
    roi = geometry.box(*burst.get_region_of_interest(ref_burst.footprint, sec_burst.footprint, asc))

    assert not roi.intersects(geometry.box(*burst_pre.footprint.bounds))
    assert roi.intersects(geometry.box(*burst_on.footprint.bounds))
    assert not roi.intersects(geometry.box(*burst_post.footprint.bounds))
