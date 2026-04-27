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
    # inscatterRadiance: muHorizon arg can be tiny-negative when r is close to rPlanet in float
    # Build commit uses rPlanet/rAtmosphere variable names (not Rg/Rt).
    ('  float muHorizon = -sqrt(1.0 - rPlanet * rPlanet / r2);',
     '  float muHorizon = -sqrt(max(0.0, 1.0 - rPlanet * rPlanet / r2));'),
    # inscatterRadiance: horizon-interpolation r0 (above AND below, both occurrences replaced)
    ('r0 = sqrt(halfCosineLaw1 + halfCosineLaw2 * mu);',
     'r0 = sqrt(max(0.0, halfCosineLaw1 + halfCosineLaw2 * mu));'),
    # groundColor: planet-horizon check can go negative when r0 < rPlanet in float
    # Build commit uses multi-line format with rPlanet/rAtmosphere (not Rg/Rt).
    ('    muSun < -sqrt(1.0 - (rPlanet * rPlanet / (r0 * r0))) ?\n'
     '    vec3(0.0) :\n'
     '    transmittance(transmittanceTexture, r0, muSun, rPlanet, rAtmosphere);',
     '    muSun < -sqrt(max(0.0, 1.0 - (rPlanet * rPlanet / (r0 * r0)))) ?\n'
     '    vec3(0.0) :\n'
     '    transmittance(transmittanceTexture, r0, muSun, rPlanet, rAtmosphere);'),
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
    '  out_color = vec4(c, 1.0);'
)
atm_out_new = (
    '  vec3 c = mix(color.rgb, inscatterColor + atmColor, opacity);\n'
    '  if (c.r != c.r || c.g != c.g || c.b != c.b) c = color.rgb;\n'
    '  out_color = vec4(c, 1.0);'
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
# Discarding pixels whose luminance < 0.15 removes the border without affecting visible content.
# Threshold 0.15 covers JPEG compression artifacts (dark grey ~15-40/255) around black backgrounds.
pc_file = 'modules/base/shaders/pointcloud/pointcloud_fs.glsl'
pc_fix_old = (
    '  vec4 textureColor = vec4(1.0);\n'
    '  if (hasSpriteTexture) {\n'
    '    fullColor *= texture(spriteTexture, vec3(texCoord, layer));\n'
    '  }'
)
# Discard near-black OR transparent pixels:
# - alpha < 0.1: catches PNGs with transparent backgrounds
# - luminance < 0.15: catches black/dark-grey backgrounds including JPEG compression artifacts
# Using OR so either condition alone is sufficient.
pc_fix_new = (
    '  vec4 textureColor = vec4(1.0);\n'
    '  if (hasSpriteTexture) {\n'
    '    textureColor = texture(spriteTexture, vec3(texCoord, layer));\n'
    '    if (textureColor.a < 0.1 || dot(textureColor.rgb, vec3(0.333)) < 0.15) discard;\n'
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

# Fix 8: Clamp u_mu in texture4D to prevent 0/0 singularity when camera is near surface.
# When rmu < 0 && delta > 0 (ray toward ground), cst.z == 0, making denominator == rho.
# When r ≈ Rg (camera near Earth surface), rho → 0 AND numerator → 0 simultaneously,
# producing 0/0 = undefined in float32. Result: u_mu gets an arbitrary value → wrong
# inscattering LUT lookup → blue flash near Earth. Clamping u_mu to [0, 1] is safe
# because the mapping is designed to stay within [0.5/N, 1-0.5/N] ⊂ [0, 1].
# NOTE: Fix 3 above already replaced sqrt(delta + cst.y) → sqrt(max(0.0, delta + cst.y))
# in the same u_mu line, so we must match the already-patched text here.
atm_common_uclamp_old = (
    '  float u_mu = cst.w + (rmu * cst.x + sqrt(max(0.0, delta + cst.y))) / (rho + cst.z) * (0.5 - 1.0 / samplesMu);\n'
    '  float u_mu_s = 0.5 / float(samplesMuS) +'
)
atm_common_uclamp_new = (
    '  float u_mu = clamp(cst.w + (rmu * cst.x + sqrt(max(0.0, delta + cst.y))) / max(rho + cst.z, 1e-4) * (0.5 - 1.0 / samplesMu), 0.0, 1.0);\n'
    '  float u_mu_s = 0.5 / float(samplesMuS) +'
)

if os.path.exists(atm_common_clamp_file):
    content = open(atm_common_clamp_file).read()
    if atm_common_uclamp_old in content:
        content = content.replace(atm_common_uclamp_old, atm_common_uclamp_new)
        open(atm_common_clamp_file, 'w').write(content)
        print('FIXED texture4D u_mu singularity clamp in ' + atm_common_clamp_file)
    else:
        print('SKIP (not found or already fixed): texture4D u_mu singularity clamp')
else:
    print('NOT FOUND: ' + atm_common_clamp_file)

# Fix 12: Clamp u_r and u_muSun in irradiance() LUT lookup in atmosphere_deferred_fs.glsl.
# After single-precision conversion, r passed to irradiance() can be slightly < rPlanet
# (e.g. when surface pixel r0 = length(x + t*v) rounds down). This gives u_r < 0.
# Also muSun passed from groundColor uses max(dotNS, 0) but muSun > 1.0 is theoretically
# possible with float rounding, giving u_muSun > 1.0.
# Without clamping, out-of-range UVs on Metal may not use GL_CLAMP_TO_EDGE correctly.
irr_file = 'modules/atmosphere/shaders/atmosphere_deferred_fs.glsl'
irr_old = (
    '  float u_r = (r - rPlanet) / (rAtmosphere - rPlanet);\n'
    '  float u_muSun = (muSun + 0.2) / 1.2;\n'
    '  return texture(s, vec2(u_muSun, u_r)).rgb;'
)
irr_new = (
    '  float u_r = clamp((r - rPlanet) / (rAtmosphere - rPlanet), 0.0, 1.0);\n'
    '  float u_muSun = clamp((muSun + 0.2) / 1.2, 0.0, 1.0);\n'
    '  return texture(s, vec2(u_muSun, u_r)).rgb;'
)

if os.path.exists(irr_file):
    content = open(irr_file).read()
    if irr_old in content:
        content = content.replace(irr_old, irr_new)
        open(irr_file, 'w').write(content)
        print('FIXED irradiance u_r/u_muSun clamp in ' + irr_file)
    else:
        print('SKIP (not found or already fixed): irradiance u_r/u_muSun clamp')
else:
    print('NOT FOUND: ' + irr_file)

# Fix 9: NaN guards in precomputed LUT shaders (delta_j, transmittance, inscattering).
# These shaders run once at startup to bake atmosphere LUT textures. On Metal,
# sqrt(negative) may return 0 instead of NaN — baking wrong finite values into the
# LUT, which then produce wrong inscattering/transmittance at runtime → blue flicker.
# Fix 6 (NaN output guard) cannot catch finite wrong values; fix them at the source.
lut_fixes = [
    # Build commit uses camelCase filenames and Rg/Rg2 variable names (not rPlanet/rPlanet2)
    ('modules/atmosphere/shaders/deltaJ_calc_fs.glsl', [
        # sinThetaSinSigma: mu*mu or muSun*muSun slightly > 1 in float32
        ('float sinThetaSinSigma = sqrt(1.0 - mu2) * sqrt(1.0 - muSun2);',
         'float sinThetaSinSigma = sqrt(max(0.0, 1.0 - mu2)) * sqrt(max(0.0, 1.0 - muSun2));'),
        # view direction vector: same mu2 issue
        ('vec3 v = vec3(sqrt(1.0 - mu2), 0.0, mu);',
         'vec3 v = vec3(sqrt(max(0.0, 1.0 - mu2)), 0.0, mu);'),
        # distanceToGround: uses Rg2 (not rPlanet2) at build commit
        ('distanceToGround = -r * cosineTheta - sqrt(r2 * (cosineTheta2 - 1.0) + Rg2);',
         'distanceToGround = -r * cosineTheta - sqrt(max(0.0, r2 * (cosineTheta2 - 1.0) + Rg2));'),
    ]),
    ('modules/atmosphere/shaders/transmittance_calc_fs.glsl', [
        # cosZenithHorizon: uses Rg (not rPlanet) at build commit
        ('float cosZenithHorizon = -sqrt(1.0 - ((Rg * Rg) / r2));',
         'float cosZenithHorizon = -sqrt(max(0.0, 1.0 - ((Rg * Rg) / r2)));'),
        # y_ii: uses Rg (not rPlanet) at build commit
        ('float y_ii = exp(-(sqrt(r2 + x_i * x_i + 2.0 * x_i * r * mu) - Rg) / H);',
         'float y_ii = exp(-(sqrt(max(0.0, r2 + x_i * x_i + 2.0 * x_i * r * mu)) - Rg) / H);'),
    ]),
    ('modules/atmosphere/shaders/inScattering_calc_fs.glsl', [
        # muSun_i horizon check: uses Rg (not rPlanet) at build commit
        ('if (muSun_i >= -sqrt(1.0 - Rg * Rg / (ri * ri))) {',
         'if (muSun_i >= -sqrt(max(0.0, 1.0 - Rg * Rg / (ri * ri)))) {'),
    ]),
    ('modules/atmosphere/shaders/inScattering_sup_calc_fs.glsl', [
        # r_i: cosine-law distance can go slightly negative at surface in float32
        ('float r_i = sqrt(r * r + dist * dist + 2.0 * r * dist * mu);',
         'float r_i = sqrt(max(0.0, r * r + dist * dist + 2.0 * r * dist * mu));'),
    ]),
]

for lut_file, fixes in lut_fixes:
    if not os.path.exists(lut_file):
        print('NOT FOUND: ' + lut_file)
        continue
    content = open(lut_file).read()
    changed = False
    for old, new in fixes:
        if old in content:
            content = content.replace(old, new)
            print('FIXED LUT guard [' + old[:55] + '...] in ' + lut_file)
            changed = True
        else:
            print('SKIP (not found or already fixed): ' + old[:55])
    if changed:
        open(lut_file, 'w').write(content)

# Fix 10: Restore double-precision model transform in atmospheredeferredcaster.
#
# Root cause of atmosphere blue flicker:
# applesilicon.diffedited.txt converts _modelTransform from dmat4 to mat4.
# Earth's model transform includes its solar-system translation (~1.5e11 m).
# float32 precision at 1.5e11 m is ~18 km (= 1.5e11 / 2^23).
# camPosObj = invModelMatrix * eyePosition inherits this ~18 km error.
# In the GLSL atmosphereIntersection(), |ray.origin| is compared to Rt (~6471 km).
# When the camera is within ~18 km of the atmosphere boundary, the test flips
# randomly frame to frame -> blue geometric shapes flicker around Earth.
#
# Fix: restore _modelTransform as dmat4, compute invModelMatrix in double,
# compute camPosObj and the full pipeline transform in double, then downcast
# to float32 only when setting the GLSL uniforms (which are float-typed).

cpp_file = 'modules/atmosphere/rendering/atmospheredeferredcaster.cpp'
h_file = 'modules/atmosphere/rendering/atmospheredeferredcaster.h'

# Fix 10a: _modelTransform field back to dmat4 in header
h_old = '    glm::mat4 _modelTransform;'
h_new = '    glm::dmat4 _modelTransform;'

if os.path.exists(h_file):
    content = open(h_file).read()
    if h_old in content:
        content = content.replace(h_old, h_new)
        open(h_file, 'w').write(content)
        print('FIXED _modelTransform restored to dmat4 in ' + h_file)
    else:
        print('SKIP (not found or already fixed): _modelTransform dmat4 in header')
else:
    print('NOT FOUND: ' + h_file)

# Fix 10b: setModelTransform — stop casting dmat4 to mat4 on store
cpp_set_old = '    _modelTransform = std::move(static_cast<glm::mat4>(transform));'
cpp_set_new = '    _modelTransform = std::move(transform);'

if os.path.exists(cpp_file):
    content = open(cpp_file).read()
    if cpp_set_old in content:
        content = content.replace(cpp_set_old, cpp_set_new)
        open(cpp_file, 'w').write(content)
        print('FIXED setModelTransform stores dmat4 in ' + cpp_file)
    else:
        print('SKIP (not found or already fixed): setModelTransform dmat4 store')
else:
    print('NOT FOUND: ' + cpp_file)

# Fix 10c: preRaycast — compute matrices and camPosObj in double, cast only for uniforms
cpp_prr_old = (
    '        // Object Space\n'
    '        glm::mat4 invModelMatrix = glm::inverse(_modelTransform);\n'
    '        prg.setUniform(_uniformCache.inverseModelTransformMatrix, invModelMatrix);\n'
    '        prg.setUniform(_uniformCache.modelTransformMatrix, _modelTransform);\n'
    '\n'
    '        glm::mat4 viewToWorldMatrix =\n'
    '            glm::inverse(static_cast<glm::mat4>(data.camera.combinedViewMatrix()));\n'
    '\n'
    '        // Eye Space to World Space\n'
    '        prg.setUniform(_uniformCache.viewToWorldMatrix, viewToWorldMatrix);\n'
    '\n'
    '        // Projection to Eye Space\n'
    '        glm::mat4 dInvProj = glm::inverse(data.camera.projectionMatrix());\n'
    '\n'
    '        glm::mat4 invWholePipeline = invModelMatrix * viewToWorldMatrix * dInvProj;\n'
    '\n'
    '        prg.setUniform(_uniformCache.projectionToModelTransform, invWholePipeline);\n'
    '\n'
    '        glm::vec4 camPosObjCoords = invModelMatrix *\n'
    '            glm::vec4(static_cast<glm::vec3>(data.camera.eyePositionVec3()), 1.0);\n'
    '        prg.setUniform(_uniformCache.camPosObj, glm::vec3(camPosObjCoords));\n'
    '\n'
    '        SceneGraphNode* node = sceneGraph()->sceneGraphNode("Sun");\n'
    '        glm::dvec3 sunPosWorld = node ? node->worldPosition() : glm::dvec3(0.0);\n'
    '\n'
    '        glm::vec3 sunPosObj;\n'
    '        // Sun following camera position\n'
    '        if (_sunFollowingCameraEnabled) {\n'
    '            sunPosObj = invModelMatrix *\n'
    '                glm::vec4(glm::vec3(data.camera.eyePositionVec3()), 1.0);\n'
    '        }\n'
    '        else {\n'
    '            sunPosObj = invModelMatrix * static_cast<glm::vec4>(\n'
    '                glm::dvec4((sunPosWorld - data.modelTransform.translation) * 1000.0, 1.0)\n'
    '            );\n'
    '        }\n'
    '\n'
    '        // Sun Position in Object Space\n'
    '        prg.setUniform(_uniformCache.sunDirectionObj, glm::normalize(sunPosObj));'
)
cpp_prr_new = (
    '        // Object Space\n'
    '        glm::dmat4 invModelMatrixD = glm::inverse(_modelTransform);\n'
    '        prg.setUniform(_uniformCache.inverseModelTransformMatrix, glm::mat4(invModelMatrixD));\n'
    '        prg.setUniform(_uniformCache.modelTransformMatrix, glm::mat4(_modelTransform));\n'
    '\n'
    '        glm::dmat4 viewToWorldMatrixD =\n'
    '            glm::inverse(data.camera.combinedViewMatrix());\n'
    '\n'
    '        // Eye Space to World Space\n'
    '        prg.setUniform(_uniformCache.viewToWorldMatrix, glm::mat4(viewToWorldMatrixD));\n'
    '\n'
    '        // Projection to Eye Space\n'
    '        glm::dmat4 dInvProj = glm::inverse(glm::dmat4(data.camera.projectionMatrix()));\n'
    '\n'
    '        glm::mat4 invWholePipeline = glm::mat4(invModelMatrixD * viewToWorldMatrixD * dInvProj);\n'
    '\n'
    '        prg.setUniform(_uniformCache.projectionToModelTransform, invWholePipeline);\n'
    '\n'
    '        glm::dvec4 camPosObjCoords = invModelMatrixD *\n'
    '            glm::dvec4(data.camera.eyePositionVec3(), 1.0);\n'
    '        prg.setUniform(_uniformCache.camPosObj, glm::vec3(camPosObjCoords));\n'
    '\n'
    '        SceneGraphNode* node = sceneGraph()->sceneGraphNode("Sun");\n'
    '        glm::dvec3 sunPosWorld = node ? node->worldPosition() : glm::dvec3(0.0);\n'
    '\n'
    '        glm::dvec3 sunPosObj;\n'
    '        // Sun following camera position\n'
    '        if (_sunFollowingCameraEnabled) {\n'
    '            sunPosObj = glm::dvec3(invModelMatrixD *\n'
    '                glm::dvec4(data.camera.eyePositionVec3(), 1.0));\n'
    '        }\n'
    '        else {\n'
    '            sunPosObj = glm::dvec3(invModelMatrixD *\n'
    '                glm::dvec4((sunPosWorld - data.modelTransform.translation) * 1000.0, 1.0));\n'
    '        }\n'
    '\n'
    '        // Sun Position in Object Space\n'
    '        prg.setUniform(_uniformCache.sunDirectionObj, glm::normalize(glm::vec3(sunPosObj)));'
)

if os.path.exists(cpp_file):
    content = open(cpp_file).read()
    if cpp_prr_old in content:
        content = content.replace(cpp_prr_old, cpp_prr_new)
        open(cpp_file, 'w').write(content)
        print('FIXED double-precision preRaycast transforms in ' + cpp_file)
    else:
        print('SKIP (not found or already fixed): double-precision preRaycast transforms')
else:
    print('NOT FOUND: ' + cpp_file)

# Fix 11: Precise view-to-object matrix for positionObjectsCoords reconstruction.
#
# Even with Fix 10, positionObjectsCoords is still imprecise:
#   vec4 positionWorldCoords = viewToWorldMatrix * position;        // view → world (~1.5e11 m)
#   vec3 positionObjectsCoords = (inverseModelTransformMatrix * positionWorldCoords).xyz;
# Both mat4 uniforms have solar-scale elements in float32 (~18 km precision).
# The two-step transform adds then subtracts ~1.5e11 m — float32 catastrophic cancellation.
# pixelDepth = length(camPosObj - positionObjectsCoords) has ~18 km error →
# atmosphere flicker when camera moves (new positionObjectsCoords each frame).
#
# Fix: precompute viewToObjectMatrix = invModel × viewToWorld in double (C++).
# The product's translation column = camPosObj (~6400 km), not ~1.5e11 m.
# Elements are small → accurate float32 uniform. GLSL uses it directly on position
# (view space) to get positionObjectsCoords without going through world space.

atm_glsl_file = 'modules/atmosphere/shaders/atmosphere_deferred_fs.glsl'

# Fix 11a: Declare viewToObjectMatrix uniform in GLSL
glsl_uni_old = (
    'uniform mat4 viewToWorldMatrix;\n'
    'uniform mat4 projectionToModelTransformMatrix;'
)
glsl_uni_new = (
    'uniform mat4 viewToWorldMatrix;\n'
    'uniform mat4 viewToObjectMatrix;\n'
    'uniform mat4 projectionToModelTransformMatrix;'
)

if os.path.exists(atm_glsl_file):
    content = open(atm_glsl_file).read()
    if glsl_uni_old in content:
        content = content.replace(glsl_uni_old, glsl_uni_new)
        open(atm_glsl_file, 'w').write(content)
        print('FIXED viewToObjectMatrix uniform declaration in ' + atm_glsl_file)
    else:
        print('SKIP (not found or already fixed): viewToObjectMatrix uniform declaration')
else:
    print('NOT FOUND: ' + atm_glsl_file)

# Fix 11b: Use viewToObjectMatrix to compute positionObjectsCoords
glsl_pos_old = (
    '  // World to Object (Normal and Position in meters)\n'
    '  vec3 positionObjectsCoords = (inverseModelTransformMatrix * positionWorldCoords).xyz;'
)
glsl_pos_new = (
    '  // World to Object (Normal and Position in meters)\n'
    '  // viewToObjectMatrix = invModel * viewToWorld, precomputed in double in C++\n'
    '  // avoids solar-scale (~1.5e11 m) float32 precision loss in two-step transform\n'
    '  vec3 positionObjectsCoords = (viewToObjectMatrix * position).xyz;'
)

if os.path.exists(atm_glsl_file):
    content = open(atm_glsl_file).read()
    if glsl_pos_old in content:
        content = content.replace(glsl_pos_old, glsl_pos_new)
        open(atm_glsl_file, 'w').write(content)
        print('FIXED positionObjectsCoords via viewToObjectMatrix in ' + atm_glsl_file)
    else:
        print('SKIP (not found or already fixed): positionObjectsCoords via viewToObjectMatrix')
else:
    print('NOT FOUND: ' + atm_glsl_file)

# Fix 11d: Add viewToObjectMatrix to UniformCache in header.
# The build commit's UniformCache does not include viewToObjectMatrix; without this,
# program.setUniform(_uniformCache.viewToObjectMatrix, ...) would not compile.
# Must run before Fix 11c (which uses _uniformCache.viewToObjectMatrix).
h_uc_old = '        projectionToModelTransformMatrix, viewToWorldMatrix, camPosObj, sunDirectionObj,'
h_uc_new = '        projectionToModelTransformMatrix, viewToWorldMatrix, viewToObjectMatrix, camPosObj, sunDirectionObj,'

if os.path.exists(h_file):
    content = open(h_file).read()
    if h_uc_old in content:
        content = content.replace(h_uc_old, h_uc_new)
        open(h_file, 'w').write(content)
        print('FIXED viewToObjectMatrix added to UniformCache in ' + h_file)
    else:
        print('SKIP (not found or already fixed): viewToObjectMatrix in UniformCache')
else:
    print('NOT FOUND: ' + h_file)

# Fix 11c: Compute and send viewToObjectMatrix from C++.
# The applesilicon patch keeps the build commit's program.setUniform calls and variable
# names (invModelMatrix, viewToWorld — both const glm::dmat4). Fix 10c was designed for
# a different code path (prg.setUniform) and SKIPS on this build commit. We therefore
# match the applesilicon-patched text directly using program.setUniform and the correct
# variable names.
cpp_vto_old = (
    '        // Eye Space to World Space\n'
    '        // Cast to float (mat4)\n'
    '        program.setUniform(_uniformCache.viewToWorldMatrix, glm::mat4(viewToWorld));\n'
    '\n'
    '        // Projection to Eye Space\n'
)
cpp_vto_new = (
    '        // Eye Space to World Space\n'
    '        // Cast to float (mat4)\n'
    '        program.setUniform(_uniformCache.viewToWorldMatrix, glm::mat4(viewToWorld));\n'
    '\n'
    '        // Precise view-to-object matrix: invModel * viewToWorld in double.\n'
    '        // Translation column = camPosObj (~6400 km), not solar-scale (~1.5e11 m).\n'
    '        // Sending as float32 is safe; used in GLSL for positionObjectsCoords.\n'
    '        glm::mat4 viewToObject = glm::mat4(invModelMatrix * viewToWorld);\n'
    '        program.setUniform(_uniformCache.viewToObjectMatrix, viewToObject);\n'
    '\n'
    '        // Projection to Eye Space\n'
)

if os.path.exists(cpp_file):
    content = open(cpp_file).read()
    if cpp_vto_old in content:
        content = content.replace(cpp_vto_old, cpp_vto_new)
        open(cpp_file, 'w').write(content)
        print('FIXED viewToObjectMatrix setUniform in preRaycast in ' + cpp_file)
    else:
        print('SKIP (not found or already fixed): viewToObjectMatrix setUniform in preRaycast')
else:
    print('NOT FOUND: ' + cpp_file)

# Fix 13: Use dotNS (actual sun angle) for sky irradiance lookup in groundColor().
#
# Bug: groundColor() clamps muSun = max(dotNS, 0) for direct illumination, then
# passes that same muSun to irradiance(). For all nightside pixels (dotNS < 0),
# muSun = 0, so every nightside pixel queries irradiance at muSun=0 = sun-at-horizon
# (maximum twilight irradiance). The entire nightside appears uniformly bright blue
# as if it were at the terminator — the "blue rectangle" artifact in screenshots.
#
# Fix: pass dotNS directly to irradiance(). Fix 12 already clamps u_muSun inside
# irradiance(), so negative dotNS safely produces minimum irradiance for deep
# nightside instead of the terminator-bright value. Direct illumination (muSun via
# max(dotNS, 0)) is unchanged — only the irradiance lookup argument changes.
irrad_mufix_file = 'modules/atmosphere/shaders/atmosphere_deferred_fs.glsl'
irrad_mufix_old = '  vec3 irradianceReflected = irradiance(irradianceTexture, r0, muSun) * irradianceFactor;'
irrad_mufix_new = '  vec3 irradianceReflected = irradiance(irradianceTexture, r0, dotNS) * irradianceFactor;'

if os.path.exists(irrad_mufix_file):
    content = open(irrad_mufix_file).read()
    if irrad_mufix_old in content:
        content = content.replace(irrad_mufix_old, irrad_mufix_new)
        open(irrad_mufix_file, 'w').write(content)
        print('FIXED irradiance uses dotNS instead of muSun in groundColor() in ' + irrad_mufix_file)
    else:
        print('SKIP (not found or already fixed): irradiance dotNS fix in groundColor()')
else:
    print('NOT FOUND: ' + irrad_mufix_file)

