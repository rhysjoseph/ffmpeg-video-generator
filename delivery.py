"""Shared editing profiles for generated patterns and file conversions."""

# id: label, encoder, encoder profile, pixel format, container
EDITING_PROFILES = {
    "prores_proxy": ("Apple ProRes Proxy", "prores_ks", "0", "yuv422p10le", "mov"),
    "prores_lt": ("Apple ProRes LT", "prores_ks", "1", "yuv422p10le", "mov"),
    "prores_422": ("Apple ProRes 422", "prores_ks", "2", "yuv422p10le", "mov"),
    "prores_hq": ("Apple ProRes 422 HQ", "prores_ks", "3", "yuv422p10le", "mov"),
    "prores_4444": ("Apple ProRes 4444", "prores_ks", "4", "yuv444p10le", "mov"),
    "prores_xq": ("Apple ProRes 4444 XQ", "prores_ks", "5", "yuv444p10le", "mov"),
    "dnxhr_lb": ("Avid DNxHR LB", "dnxhd", "dnxhr_lb", "yuv422p", "mov"),
    "dnxhr_sq": ("Avid DNxHR SQ", "dnxhd", "dnxhr_sq", "yuv422p", "mov"),
    "dnxhr_hq": ("Avid DNxHR HQ", "dnxhd", "dnxhr_hq", "yuv422p", "mov"),
    "dnxhr_hqx": ("Avid DNxHR HQX", "dnxhd", "dnxhr_hqx", "yuv422p10le", "mov"),
    "dnxhr_444": ("Avid DNxHR 444", "dnxhd", "dnxhr_444", "yuv444p10le", "mov"),
}


def generation_profiles():
    return {key: {"label": label, "encoder": encoder, "container": container,
                  "pixel_format": pixel, "bit_depth": 10 if "10le" in pixel else 8,
                  "chroma": pixel[3:6]}
            for key, (label, encoder, _, pixel, container) in EDITING_PROFILES.items()}
