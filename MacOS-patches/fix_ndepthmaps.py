import os

files = [
    'modules/globebrowsing/shaders/globalrenderer_vs.glsl',
    'modules/globebrowsing/shaders/localrenderer_vs.glsl',
    'modules/globebrowsing/shaders/renderer_fs.glsl',
]
OLD = '#define nDepthMaps #{nDepthMaps}'
NEW = '#define nDepthMaps 0'

for f in files:
    if not os.path.exists(f):
        print('NOT FOUND: ' + f)
        continue
    content = open(f).read()
    if OLD in content:
        open(f, 'w').write(content.replace(OLD, NEW))
        print('FIXED: ' + f)
    else:
        print('Pattern absent (already fixed or different): ' + f)
        print('  Lines 30-35: ' + repr(content.splitlines()[29:35]))
