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

# Fix 2: Protect atmosphere shader sqrt calls from NaN when argument goes slightly negative
# due to float rounding after single-precision patches convert double->float arithmetic.
# All four guards below apply to atmosphere_deferred_fs.glsl.
atm_file = 'modules/atmosphere/shaders/atmosphere_deferred_fs.glsl'
atm_fixes = [
    # atmosphereIntersection: r2-m2 can be tiny-negative in float
    ('float q = sqrt(r2 - m2);',
     'float q = sqrt(max(0.0, r2 - m2));'),
    # inscatterRadiance: muHorizon arg can be tiny-negative when r is close to Rg in float
    ('float muHorizon = -sqrt(1.0 - Rg*Rg / r2);',
     'float muHorizon = -sqrt(max(0.0, 1.0 - Rg*Rg / r2));'),
    # inscatterRadiance: horizon-interpolation r0 (above AND below, both occurrences replaced)
    ('r0 = sqrt(halfCosineLaw1 + halfCosineLaw2 * mu);',
     'r0 = sqrt(max(0.0, halfCosineLaw1 + halfCosineLaw2 * mu));'),
    # groundColor: planet-horizon check can go negative when r0 < Rg in float
    ('muSun < -sqrt(1.0 - (Rg*Rg / (r0 * r0)))  ?  vec3(0.0)  :  transmittance(transmittanceTexture, r0, muSun, Rg, Rt);',
     'muSun < -sqrt(max(0.0, 1.0 - (Rg*Rg / (r0 * r0))))  ?  vec3(0.0)  :  transmittance(transmittanceTexture, r0, muSun, Rg, Rt);'),
]

if os.path.exists(atm_file):
    content = open(atm_file).read()
    changed = False
    for old, new in atm_fixes:
        if old in content:
            content = content.replace(old, new)
            print('FIXED atm NaN guard [' + old[:50] + '...] in ' + atm_file)
            changed = True
        else:
            print('SKIP (not found or already fixed): ' + old[:50])
    if changed:
        open(atm_file, 'w').write(content)
else:
    print('NOT FOUND: ' + atm_file)

# Fix 3: NaN guards in atmosphere_common.glsl (included by atmosphere_deferred_fs.glsl).
# These functions are called per-pixel at runtime; float precision makes sqrt args go
# slightly negative when surface fragment r0 ≈ Rg, producing NaN → blue flicker.
atm_common_file = 'modules/atmosphere/shaders/atmosphere_common.glsl'
atm_common_fixes = [
    # texture4D: most critical — surface fragment r0 can compute as r0 < Rg in float
    ('float rho = sqrt(r2 - Rg2);',
     'float rho = sqrt(max(0.0, r2 - Rg2));'),
    # texture4D: delta + cst.y can be tiny-negative near tangent rays in float
    ('sqrt(delta + cst.y)',
     'sqrt(max(0.0, delta + cst.y))'),
    # transmittance LUT lookup: u_r NaN when r < Rg in float
    ('float u_r = sqrt((r - Rg) / (Rt - Rg));',
     'float u_r = sqrt(max(0.0, (r - Rg) / (Rt - Rg)));'),
    # transmittance along ray: cosine-law distance, tiny-negative with float rounding
    ('float ri = sqrt(d * d + r * r + 2.0 * r * d * mu);',
     'float ri = sqrt(max(0.0, d * d + r * r + 2.0 * r * d * mu));'),
]

if os.path.exists(atm_common_file):
    content = open(atm_common_file).read()
    changed = False
    for old, new in atm_common_fixes:
        if old in content:
            content = content.replace(old, new)
            print('FIXED atm_common NaN guard [' + old[:50] + '...] in ' + atm_common_file)
            changed = True
        else:
            print('SKIP (not found or already fixed): ' + old[:50])
    if changed:
        open(atm_common_file, 'w').write(content)
else:
    print('NOT FOUND: ' + atm_common_file)
