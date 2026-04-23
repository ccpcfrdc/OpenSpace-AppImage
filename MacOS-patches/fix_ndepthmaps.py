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

# Fix 5: Clamp exp argument in opticalDepth to prevent float32 overflow → infinity.
# exp(a01sq.x) where a01sq.x can reach ~375 for Earth surface geometry; float32 max
# exp is ~exp(88). exp(375) → infinity → analyticTransmittance → 0 → full inscattering
# → blue flicker over Earth surface. Clamping to 85.0 keeps result finite.
atm_exp_file = 'modules/atmosphere/shaders/atmosphere_deferred_fs.glsl'
atm_exp_old = '  float x = a01s.y > a01s.x ? exp(a01sq.x) : 0.0;'
atm_exp_new = '  float x = a01s.y > a01s.x ? exp(min(a01sq.x, 85.0)) : 0.0;'

if os.path.exists(atm_exp_file):
    content = open(atm_exp_file).read()
    if atm_exp_old in content:
        content = content.replace(atm_exp_old, atm_exp_new)
        open(atm_exp_file, 'w').write(content)
        print('FIXED opticalDepth exp overflow guard in ' + atm_exp_file)
    else:
        print('SKIP (not found or already fixed): opticalDepth exp overflow guard')
else:
    print('NOT FOUND: ' + atm_exp_file)

# Fix 6: NaN safety net at atmosphere output — any remaining NaN falls back to G-buffer color.
# NaN != NaN in GLSL, so (c != c) detects NaN components. This catches any NaN source
# not covered by individual guards above.
atm_out_old = (
    '  vec3 c = mix(color.rgb, inscatterColor + atmColor, opacity);\n'
    '  renderTarget = vec4(c, 1.0);'
)
atm_out_new = (
    '  vec3 c = mix(color.rgb, inscatterColor + atmColor, opacity);\n'
    '  if (c.r != c.r || c.g != c.g || c.b != c.b) c = color.rgb;\n'
    '  renderTarget = vec4(c, 1.0);'
)

if os.path.exists(atm_exp_file):
    content = open(atm_exp_file).read()
    if atm_out_old in content:
        content = content.replace(atm_out_old, atm_out_new)
        open(atm_exp_file, 'w').write(content)
        print('FIXED atmosphere NaN output guard in ' + atm_exp_file)
    else:
        print('SKIP (not found or already fixed): atmosphere NaN output guard')
else:
    print('NOT FOUND: ' + atm_exp_file)

# Fix 4: Discard near-black pixels in pointcloud sprite texture sampling.
# On Apple Silicon (Metal backend), additive blending via glBlendFunc(GL_SRC_ALPHA, GL_ONE)
# does not suppress black texels — black borders appear around galaxy images (e.g. Tully).
# Discarding pixels whose luminance < 0.005 removes the border without affecting visible content.
pc_file = 'modules/base/shaders/pointcloud/pointcloud_fs.glsl'
pc_fix_old = (
    '  vec4 textureColor = vec4(1.0);\n'
    '  if (hasSpriteTexture) {\n'
    '    fullColor *= texture(spriteTexture, vec3(texCoord, layer));\n'
    '  }'
)
# Discard near-black OR transparent pixels:
# - alpha < 0.1: catches PNGs with transparent backgrounds (even with non-black RGB)
# - luminance < 0.05: catches black-background PNGs (including slightly grey JPEG artifacts)
# Using OR so either condition alone is sufficient.
pc_fix_new = (
    '  vec4 textureColor = vec4(1.0);\n'
    '  if (hasSpriteTexture) {\n'
    '    textureColor = texture(spriteTexture, vec3(texCoord, layer));\n'
    '    if (textureColor.a < 0.1 || dot(textureColor.rgb, vec3(0.333)) < 0.05) discard;\n'
    '    fullColor *= textureColor;\n'
    '  }'
)

if os.path.exists(pc_file):
    content = open(pc_file).read()
    if pc_fix_old in content:
        content = content.replace(pc_fix_old, pc_fix_new)
        open(pc_file, 'w').write(content)
        print('FIXED pointcloud black border discard in ' + pc_file)
    else:
        print('SKIP (not found or already fixed): pointcloud black border discard')
else:
    print('NOT FOUND: ' + pc_file)

# Fix 7: Clamp UV coordinates in transmittance LUT lookups in atmosphere_common.glsl.
# On Metal, texture sampling with out-of-range UVs (e.g. u_mu ≈ -0.985 for mu=-1) may
# not clamp to edge — it can wrap or return wrong values depending on sampler state.
# Explicit clamp(uv, 0.0, 1.0) guarantees correct edge behavior on all backends.
atm_common_clamp_file = 'modules/atmosphere/shaders/atmosphere_common.glsl'
atm_common_clamp_fixes = [
    # 4-argument transmittance(): atan-based u_mu can be slightly outside [0,1]
    ('  return texture(tex, vec2(u_mu, u_r)).rgb;\n}',
     '  return texture(tex, clamp(vec2(u_mu, u_r), 0.0, 1.0)).rgb;\n}'),
]

if os.path.exists(atm_common_clamp_file):
    content = open(atm_common_clamp_file).read()
    changed = False
    for old, new in atm_common_clamp_fixes:
        if old in content:
            content = content.replace(old, new)
            print('FIXED transmittance UV clamp in ' + atm_common_clamp_file)
            changed = True
        else:
            print('SKIP (not found or already fixed): transmittance UV clamp')
    if changed:
        open(atm_common_clamp_file, 'w').write(content)
else:
    print('NOT FOUND: ' + atm_common_clamp_file)
