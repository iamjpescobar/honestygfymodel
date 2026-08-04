from styles.kc_theme import coming_soon_page

# NOTE: no st.set_page_config here — app.py already sets it once for the
# whole app, and these pages render inside that same run.
#
# This page used to be 51 lines of markup identical to the other two
# coming-soon pages apart from the strings below. The layout now lives in
# kc_theme.coming_soon_page(), so a copy edit to the shared promise lands
# on all three at once instead of drifting between them.

# Theme injection lives in app.py, which renders once per script run
# before this view is exec'd. It used to be called here as well, so the
# same ~26KB of inline CSS was serialised, shipped and parsed TWICE on
# every rerun of every page. Same cascade either way (the two layers
# overlap only on properties resolved by specificity), so the second
# copy bought nothing.

coming_soon_page(
    sport='NBA',
    emoji='🏀',
    blurb_tail='Nothing ships on this page until its data engine is real.',
    planned=[
        ('Game Cards',
         'Matchup pages for every slate — team ratings, pace, and lineup context'),
        ('Player Analytics',
         'Usage, shot quality, and matchup-driven player breakdowns'),
        ('Prop Models',
         'Composite scores built the same way the MLB engines were'),
    ],
)
