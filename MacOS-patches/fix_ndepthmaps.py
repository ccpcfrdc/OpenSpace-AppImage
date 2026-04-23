import os
import re

# Fix 1: Resolve unresolved shader template variables in globebrowsing shaders
# (these are added by single-precision patches but not set in C++ at commit 296081379b)
globebrowsing_files = [
    'modules/globebrowsing/shaders/globalrenderer_vs.glsl',
    'modules/globebrowsing/shaders/localrenderer_vs.glsl',
    'modules/globebrowsing/shaders/renderer_fs.glsl',
]

gb_replacements = [
    ('#define nDepthMaps #{nDepthMaps}', '#define nDepthMaps 0'),
    ('#define USE_DEPTHMAP_SHADOWS #{useDepthmapShadows}', '#define USE_DEPTHMAP_SHADOWS 0'),
]

for f in globebrowsing_files:
    if not os.path.exists(f):
        print('NOT FOUND: ' + f)
        continue
    content = open(f).read()
    changed = False
    for old, new in gb_replacements:
        if old in content:
            content = content.replace(old, new)
            print('FIXED [' + old[:40] + '...] in ' + f)
            changed = True
    if changed:
        open(f, 'w').write(content)
    remaining = re.findall(r'#\{[^}]+\}', content)
    if remaining:
        print('WARNING remaining templates in ' + f + ': ' + str(remaining))
    else:
        print('OK (no unresolved templates): ' + f)

# Fix 2: Protect atmosphere sqrt from NaN when r2-m2 is slightly negative due to float rounding
# After single-precision patches, atmosphereIntersection uses float but lacks max(0.0,...) guard
atm_file = 'modules/atmosphere/shaders/atmosphere_deferred_fs.glsl'
ATM_OLD = 'float q = sqrt(r2 - m2);'
ATM_NEW = 'float q = sqrt(max(0.0, r2 - m2));'

if os.path.exists(atm_file):
    content = open(atm_file).read()
    if ATM_OLD in content:
        open(atm_file, 'w').write(content.replace(ATM_OLD, ATM_NEW))
        print('FIXED atmosphere sqrt NaN guard in ' + atm_file)
    else:
        print('atmosphere sqrt already guarded or not found in ' + atm_file)
else:
    print('NOT FOUND: ' + atm_file)
