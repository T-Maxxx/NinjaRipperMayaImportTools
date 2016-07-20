import maya.cmds as cmds
import struct
import os
import os.path
import maya.OpenMaya as OpenMaya
import maya.cmds as cmds
import maya.mel as mel
import unicodedata
import _winreg as reg

RipSignature = 0xDEADC0DE
RipFileVersion = 4

InitialDirectory = ""

# Global vars.
g_VertexFormatRecog = 0  # Auto/Manual  (0,1).
g_Tex0_FileLev = 0

g_Mesh_Index = 0  # For renaming purposes.

VertexLayout = {
    'pos': [0, 1, 2],
    'nml': [3, 4, 5],
    'uv': [6, 7],
    'posUpdated': False,
    'nmlUpdated': False,
    'uvUpdated': False,
}

# Globals additional.
mdlscaler = 100
g_ninjarotX = 90
g_ninjarotY = 0
g_ninjarotZ = 0
uvscaler = 1

g_flipUV = 1
g_normalizeUV = False

g_enabler = True

RegisterKey = None


def readULong(f):
    return struct.unpack('<L', f.read(4))[0]


def readLong(f):
    return struct.unpack('<l', f.read(4))[0]


def readFloat(f):
    return struct.unpack('<f', f.read(4))[0]


def readString(f):
    s = ""
    while True:
        b = f.read(1)
        if b == chr(0):
            break
        s = s + b
    return s


def printMessage(text):
    mel.eval('print "// {} //"'.format(text))


def regReadFloat(keyName):
    return float(regReadString(keyName))


def regReadDword(keyName):
    return reg.QueryValueEx(RegisterKey, keyName)[0]


def regReadString(keyName):
    return regReadDword(keyName).encode('ascii', 'ignore')


def regReadBool(keyName):
    return bool(regReadDword(keyName))


def regSetDword(keyName, val):
    reg.SetValueEx(RegisterKey, keyName, 0, reg.REG_DWORD, val)


def regSetString(keyName, val):
    reg.SetValueEx(RegisterKey, keyName, 0, reg.REG_SZ, val)


def regSetFloat(keyName, val):
    regSetString(keyName, "{}".format(val))


def regSetBool(keyName, val):
    regSetDword(keyName, 1 if val else 0)


def readRIPHeader(f):
    return struct.unpack('<LLLLLLLL', f.read(32))[0]


def updateVertexLayoutIndexes(t, baseIndex):
    if t is None:
        return

    global VertexLayout

    key = "{}Updated".format(t)

    if VertexLayout[key] is False:
        VertexLayout[t][0] = baseIndex
        VertexLayout[t][1] = baseIndex + 1
        VertexLayout[t][2] = baseIndex + 2
        VertexLayout[key] = True


def readRIPVertexAttrib(f, count):
    result = ''
    types = {0: 'f', 1: 'L', 2: 'l'}
    vertexAttributes = []

    for i in range(count):
        semantic = readString(f)
        semanticIndex = readULong(f)
        offset = readULong(f)
        size = readULong(f)
        typeMapElements = readULong(f)
        for j in range(typeMapElements):
            result += types.get(readULong(f), 1)

        vertexAttributes.append([semantic, offset / 4])

    if g_VertexFormatRecog == 0:  # AUTO recognition.
        applyRecognitionLogic(vertexAttributes)

    return result


def applyRecognitionLogic(vertexAttributes):
    isPosIdxSet = False
    isNormalIdxSet = False
    isTexCoordSet = False
    shortNames = {'POSITION': 'pos', 'NORMAL': 'nml', 'TEXCOORD': 'uv'}

    for i in range(len(vertexAttributes)):
        updateVertexLayoutIndexes(
            shortNames[vertexAttributes[i][0]], vertexAttributes[i][1]
        )


def readRIPStrings(f, count):
    result = []
    for i in range(count):
        result.append(readString(f))

    return result


def readRIPFaces(f, count):
    faceArray = OpenMaya.MIntArray()
    for i in range(count):
        data = struct.unpack('LLL', f.read(12))
        for j in range(3):
            result.append(data[j])

    return faceArray


def readRIPVertexes(f, count, vertDict):
    result = []

    Vert_array = OpenMaya.MFloatPointArray()
    Normal_array = []
    UArray = OpenMaya.MFloatArray()
    VArray = OpenMaya.MFloatArray()

    rawStructSize = len(vertDict) * 4
    for i in range(count):
        vertexData = struct.unpack(vertDict, f.read(rawStructSize))

        Vert_array.append(
            vertexData[VertexLayout['pos'][0]],
            vertexData[VertexLayout['pos'][1]],
            vertexData[VertexLayout['pos'][2]]
        )
        Normal_array.append(
            [
                vertexData[VertexLayout['nml'][0]],
                vertexData[VertexLayout['nml'][1]],
                vertexData[VertexLayout['nml'][2]]
            ]
        )
        UArray.append(vertexData[VertexLayout['uv'][0]])
        VArray.append(1 - vertexData[VertexLayout['uv'][1]])

    # VertexData:
    # [0] - Vert_array
    # [1] - Normal_array
    # [2] - UArray
    # [3] - VArray
    result.append(Vert_array)
    result.append(Normal_array)
    result.append(UArray)
    result.append(VArray)
    return result


def isFileReadCorrect(h, v, f):
    return h[3] == v[0].length() and h[2] == f.length() / 3


def importRip(path):
    global g_VertexFormatRecog
    global mdlscaler
    global uvscaler
    global g_flipUV
    global g_Tex0_FileLev

    with open(path, "rb") as f:
        header = readRIPHeader(f)
        # Header:
        # [0] - signature
        # [1] - version
        # [2] - dwFacesCnt
        # [3] - dwVertexesCnt
        # [4] - VertexSize
        # [5] - TextureFilesCnt
        # [6] - ShaderFilesCnt
        # [7] - VertexAttributesCnt

        if header[0] != RipSignature or header[1] != RipFileVersion:
            printMessage(
                "Expected signature '{}' (got '{}')".format(
                    RipSignature, signature
                )
            )

            printMessage(
                "Expected version '{}' (got '{}')".format(
                    RipFileVersion, version
                )
            )

            printMessage("File '{}' is nor a RIP file".format(path))
            return

        # print("*****ImportRip() File: " + path)
        # print("dwFacesCnt=" + str(dwFacesCnt))
        # print("dwVertexesCnt=" + str(dwVertexesCnt))
        # print("VertexAttributesCnt=" + str(VertexAttributesCnt))

        Normal_array = []
        Vert_array = OpenMaya.MFloatPointArray()
        UArray = OpenMaya.MFloatArray()
        VArray = OpenMaya.MFloatArray()

        # Read vertex attributes.
        vertexStructDictionary = readRIPVertexAttrib(f, header[7])
        # Read textures list (if present).
        TextureFiles = readRIPTextures(f, header[5])
        # Read shader list (if present).
        ShaderFiles = readRIPTextures(f, header[6])
        # Read mesh faces.
        Face_array = readRIPFaces(f, header[2])
        # Read vertexes data.
        VertexData = readRIPVertexes(f, header[3], vertexStructDictionary)
        # VertexData:
        # [0] - Vert_array
        # [1] - Normal_array
        # [2] - UArray
        # [3] - VArray

        print("---------Importing RIP file---------------------")
        print("g_VertexFormatRecog = {}".format(g_VertexFormatRecog))
        print("VertexLayout['pos'][0] = {}".format(VertexLayout['pos'][0]))
        print("VertexLayout['pos'][1] = {}".format(VertexLayout['pos'][1]))
        print("VertexLayout['pos'][2] = {}".format(VertexLayout['pos'][2]))
        print("VertexLayout['nml'][0] = {}".format(VertexLayout['nml'][0]))
        print("VertexLayout['nml'][1] = {}".format(VertexLayout['nml'][1]))
        print("VertexLayout['nml'][2] = {}".format(VertexLayout['nml'][2]))
        print("VertexLayout['uv'][0] = {}".format(VertexLayout['uv'][0]))
        print("VertexLayout['uv'][1] = {}".format(VertexLayout['uv'][1]))
        print("mdlscaler = {}".format(mdlscaler))
        print("uvscaler = {}".format(uvscaler))
        print("g_Tex0_FileLev = {}".format(g_Tex0_FileLev))
        print("g_flipUV = {}".format(g_flipUV))

    textureFile = "setka.png"
    if TextureFiles:
        textureFile = TextureFiles[g_Tex0_FileLev]

    if isFileReadCorrect(header, VertexData, Face_array):
        ImportToMaya(
            VertexData[0], Face_array, [VertexData[2], VertexData[3]],
            os.path.dirname(path), textureFile
        )
        return
    printMessage("File reading error: incomplete vertex/faces arrays.")


def ImportToMaya(vertexArray, polygonConnects, uvArray, texturePath, texture):
    global g_Mesh_Index

    polygonCounts = OpenMaya.MIntArray(polygonConnects.length() / 3, 3)
    mesh = OpenMaya.MFnMesh()
    transform = mesh.create(
        vertexArray.length(), polygonCounts.length(), vertexArray,
        polygonCounts, polygonConnects
    )

    # UV map.
    mesh.setUVs(uvArray[0], uvArray[1])
    mesh.assignUVs(polygonCounts, polygonConnects)

    # Rename mesh.
    transformDagPath = OpenMaya.MDagPath()
    OpenMaya.MDagPath.getAPathTo(transform, transformDagPath)
    meshName = cmds.rename(
        transformDagPath.fullPathName(), "NinjaMesh_{}".format(g_Mesh_Index)
    )
    g_Mesh_Index = g_Mesh_Index + 1

    # Apply textures.
    shader = cmds.shadingNode(
        "lambert", name="NinjaTexture_{}".format(g_Mesh_Index), asShader=True
    )

    cmds.select(meshName)
    cmds.hyperShade(assign=shader)

    colorMap = cmds.shadingNode(
        "file", name="{}_colorMap".format(texture), asTexture=True
    )

    cmds.connectAttr(
        "{}.outColor".format(colorMap), "{}.color".format(shader)
    )
    cmds.setAttr(
        "{}.fileTextureName".format(colorMap),
        "{}/{}".format(texturePath, texture), type='string'
    )

    # Set vertex color to White.
    cmds.select(meshName)
    cmds.polyColorPerVertex(cdo=True, rgb=[1, 1, 1])

    # Apply transformations.
    cmds.setAttr("{}.rotateX".format(meshName), g_ninjarotX)
    cmds.setAttr("{}.rotateY".format(meshName), g_ninjarotY)
    cmds.setAttr("{}.rotateZ".format(meshName), g_ninjarotZ)
    cmds.setAttr("{}.scaleX".format(meshName), mdlscaler)
    cmds.setAttr("{}.scaleY".format(meshName), mdlscaler)
    cmds.setAttr("{}.scaleZ".format(meshName), mdlscaler)

    # Freeze transformations.
    cmds.makeIdentity(apply=True, t=1, r=1, s=1, n=0, pn=1)

    # Scale UVs.
    uvs = cmds.polyListComponentConversion(meshName, tuv=True)
    cmds.select(uvs)
    cmds.polyEditUV(su=uvscaler, sv=uvscaler*g_flipUV)

    # Normalize UV.
    if g_normalizeUV:
        cmds.polyNormalizeUV(nt=1, pa=True, centerOnTile=True)

    # Merge duplicates.
    cmds.select(cl=True)
    cmds.select(meshName)
    cmds.polyMergeVertex(d=0.01, am=True, ch=1)
    cmds.polyMergeUV(d=0.01, ch=True)

    cmds.select(cl=True)
    print("Import done for mesh '{}'".format(meshName))


def changeVertexRecognition(isManual):
    global g_VertexFormatRecog
    g_VertexFormatRecog = int(state)
    cmds.frameLayout('NR_VertexLayout_Position', edit=True, en=False)
    cmds.frameLayout('NR_VertexLayout_Normal', edit=True, en=state)
    cmds.frameLayout('NR_VertexLayout_TexCoord', edit=True, en=state)


def onImportButtonPressed():
    global InitialDirectory
    global VertexLayout

    global mdlscaler
    global g_ninjarotX
    global g_ninjarotY
    global g_ninjarotZ
    global uvscaler

    global g_Tex0_FileLev
    global g_flipUV
    global g_normalizeUV

    mdlscaler = cmds.floatField('NR_TransformScale', query=True, v=True)
    g_ninjarotX = cmds.floatField('NR_TransformRotateX', query=True, v=True)
    g_ninjarotY = cmds.floatField('NR_TransformRotateY', query=True, v=True)
    g_ninjarotZ = cmds.floatField('NR_TransformRotateZ', query=True, v=True)
    uvscaler = cmds.floatField('NR_TransformUVScale', query=True, v=True)

    g_Tex0_FileLev = cmds.intField('NR_MiscTextureNumber', query=True, v=True)
    if cmds.checkBox('NR_MiscFlipUV', query=True, v=True):
        g_flipUV = -1
    else:
        g_flipUV = 1

    g_normalizeUV = cmds.checkBox('NR_MiscNormalizeUV', query=True, v=True)

    if g_VertexFormatRecog == 1:
        VertexLayout['pos'][0] = cmds.intField(
            'NR_VertexLayout_PosX', query=True, v=True
        )
        VertexLayout['pos'][1] = cmds.intField(
            'NR_VertexLayout_PosY', query=True, v=True
        )
        VertexLayout['pos'][2] = cmds.intField(
            'NR_VertexLayout_PosZ', query=True, v=True
        )
        VertexLayout['nml'][0] = cmds.intField(
            'NR_VertexLayout_NmlX', query=True, v=True
        )
        VertexLayout['nml'][1] = cmds.intField(
            'NR_VertexLayout_NmlY', query=True, v=True
        )
        VertexLayout['nml'][2] = cmds.intField(
            'NR_VertexLayout_NmlZ', query=True, v=True
        )
        VertexLayout['uv'][0] = cmds.intField(
            'NR_VertexLayout_TCU', query=True, v=True
        )
        VertexLayout['uv'][1] = cmds.intField(
            'NR_VertexLayout_TCV', query=True, v=True
        )

    saveOptions()

    fileList = cmds.fileDialog2(
        fileMode=4, fileFilter="RIP Files (*.rip)",
        caption="Select .rip files...", dir=InitialDirectory
    )

    if fileList is None:
        printMessage("No files selected")
        return

    for i in range(0, len(fileList)):
        fileList[i] = fileList[i].encode('ascii', 'ignore')
        importRip(fileList[i])

    InitialDirectory = os.path.dirname(fileList[0])
    printMessage("Import done.")


def createMenu():
    cmds.setParent(mel.eval("$temp1=$gMainWindow"))

    if cmds.control('NR_ImportMenu', exists=True):
        cmds.deleteUI('NR_ImportMenu', menu=True)

    menu = cmds.menu('NR_ImportMenu', label='Ninja Ripper', tearOff=True)

    cmds.menuItem(
        label='Import RIP v4', c="cmds.showWindow('NR_ImportWindow')"
    )

    cmds.menuItem(
        label="Reload Script", c="reload(NinjaRipperMayaImportTools)"
    )


def createImportWindow():
    if cmds.control('NR_ImportWindow', exists=True):
        cmds.deleteUI('NR_ImportWindow')

    wnd = cmds.window(
        'NR_ImportWindow', title='Import RIP v4', ret=True, mxb=False,
        rtf=True, s=False
    )
    formMain = cmds.formLayout()

    # Controls.
    # Vertex layout group.
    vertexLayoutGroup = cmds.frameLayout(
        'vertexLayoutGroup', label='Vertex layout'
    )

    cmds.rowLayout(nc=2, rat=[(1, "top", 0), (2, "top", 0)])
    cmds.radioCollection()
    cmds.radioButton(
        'NR_VertexRecognitionAuto', label='Auto', sl=True,
        onc='NinjaRipperMayaImportTools.changeVertexRecognition(False)'
    )
    cmds.radioButton(
        'NR_VertexRecognitionManual', label='Manual',
        onc='NinjaRipperMayaImportTools.changeVertexRecognition(True)'
    )

    cmds.setParent('..')

    cmds.columnLayout(adj=1)

    cmds.frameLayout('NR_VertexLayout_Position', label='Position')

    cmds.rowLayout(nc=2, adj=2)
    cmds.text(label='x:')
    cmds.intField('NR_VertexLayout_PosX', min=0, max=50, v=0, en=False)
    cmds.setParent('..')

    cmds.rowLayout(nc=2, adj=2)
    cmds.text(label='y:')
    cmds.intField('NR_VertexLayout_PosY', min=0, max=50, v=1, en=False)
    cmds.setParent('..')

    cmds.rowLayout(nc=2, adj=2)
    cmds.text(label='z:')
    cmds.intField('NR_VertexLayout_PosZ', min=0, max=50, v=2, en=False)
    cmds.setParent('..')

    cmds.setParent('..')

    cmds.frameLayout('NR_VertexLayout_Normal', label='Normal')

    cmds.rowLayout(nc=2, adj=2)
    cmds.text(label="x:")
    cmds.intField('NR_VertexLayout_NmlX', min=0, max=50, v=3)
    cmds.setParent('..')

    cmds.rowLayout(nc=2, adj=2)
    cmds.text(label="y:")
    cmds.intField('NR_VertexLayout_NmlY', min=0, max=50, v=4)
    cmds.setParent('..')

    cmds.rowLayout(nc=2, adj=2)
    cmds.text(label="z:")
    cmds.intField('NR_VertexLayout_NmlZ', min=0, max=50, v=5)
    cmds.setParent('..')

    cmds.setParent('..')

    cmds.frameLayout('NR_VertexLayout_TexCoord', label='Texture coordinates')

    cmds.rowLayout(nc=2, adj=2)
    cmds.text(label="u:")
    cmds.intField('NR_VertexLayout_TCU', min=0, max=50, v=6)
    cmds.setParent('..')

    cmds.rowLayout(nc=2, adj=2)
    cmds.text(label="v:")
    cmds.intField('NR_VertexLayout_TCV', min=0, max=50, v=7)
    cmds.setParent('..')

    cmds.setParent('..')

    cmds.setParent('..')

    cmds.setParent('..')

    # Transformations group.
    transformationsGroup = cmds.frameLayout(
        'transformationsGroup', label='Transformations'
    )

    cmds.rowLayout(nc=2, cl2=['right', 'left'], adj=2)
    cmds.text(label="Scale:", w=50)
    cmds.floatField('NR_TransformScale', min=0, v=100, pre=2)
    cmds.setParent('..')

    cmds.rowLayout(nc=2, cl2=['right', 'left'], adj=2)
    cmds.text(label="Rotate X:", w=50)
    cmds.floatField('NR_TransformRotateX', min=0, max=360, v=90.0, pre=2)
    cmds.setParent('..')

    cmds.rowLayout(nc=2, cl2=['right', 'left'], adj=2)
    cmds.text(label="Rotate Y:", w=50)
    cmds.floatField('NR_TransformRotateY', min=0, max=360, v=0.0, pre=2)
    cmds.setParent('..')

    cmds.rowLayout(nc=2, cl2=['right', 'left'], adj=2)
    cmds.text(label="Rotate Z:", w=50)
    cmds.floatField('NR_TransformRotateZ', min=0, max=360, v=0.0, pre=2)
    cmds.setParent('..')

    cmds.rowLayout(nc=2, cl2=['right', 'left'], adj=2)
    cmds.text(label="UV scale:", w=50)
    cmds.floatField('NR_TransformUVScale', min=0, v=1, pre=5)
    cmds.setParent('..')

    cmds.setParent('..')

    # Miscellaneous group.
    miscGroup = cmds.frameLayout('miscGroup', label='Miscellaneous')

    cmds.columnLayout(adj=1)
    cmds.rowLayout(nc=2, columnAlign2=['right', 'left'], adj=2)
    cmds.text(label="Texture number:")
    cmds.intField('NR_MiscTextureNumber', min=0)
    cmds.setParent('..')

    cmds.checkBox('NR_MiscFlipUV', label="Flip UV vertical")
    cmds.checkBox(
        'NR_MiscNormalizeUV', label="Normalize UV",
        ann="Works only with correct UV scale (UV set must be placed" +
            " inside (-1;-1)x(1;1) square). It may broke UV set otherwise."
    )

    cmds.setParent('..')

    cmds.setParent('..')

    # Import button.
    importButton = cmds.button(
        'importButton', label='Import file(s)...',
        c="NinjaRipperMayaImportTools.onImportButtonPressed()"
    )

    # Setup form.
    cmds.formLayout(formMain, edit=True, attachForm=[
            (vertexLayoutGroup, "left", 4), (vertexLayoutGroup, "top", 4),
            (vertexLayoutGroup, "bottom", 4),

            (transformationsGroup, "right", 4),
            (transformationsGroup, "top", 4),

            (miscGroup, "right", 4),

            (importButton, "right", 4), (importButton, "bottom", 4),
        ], attachControl=[
            (transformationsGroup, "left", 4, vertexLayoutGroup),

            (miscGroup, "top", 4, transformationsGroup),
            (miscGroup, "left", 4, vertexLayoutGroup),

            (importButton, "top", 4, miscGroup),
            (importButton, "left", 4, vertexLayoutGroup),
        ]
    )


def loadOptions():
    global g_VertexFormatRecog
    global InitialDirectory

    global VertexLayout

    global mdlscaler
    global g_ninjarotX
    global g_ninjarotY
    global g_ninjarotZ
    global uvscaler

    global g_Tex0_FileLev
    global g_flipUV
    global g_normalizeUV

    g_VertexFormatRecog = regReadDword('NR_VertexRecognition')
    InitialDirectory = regReadString('InitialDirectory')

    # VertexLayout['pos'][0] = regReadDword('NR_VertexLayout_PosX')
    # VertexLayout['pos'][2] = regReadDword('NR_VertexLayout_PosY')
    # VertexLayout['pos'][3] = regReadDword('NR_VertexLayout_PosZ')

    VertexLayout['nml'][0] = regReadDword('NR_VertexLayout_NmlX')
    VertexLayout['nml'][1] = regReadDword('NR_VertexLayout_NmlY')
    VertexLayout['nml'][2] = regReadDword('NR_VertexLayout_NmlZ')
    VertexLayout['uv'][0] = regReadDword('NR_VertexLayout_TCU')
    VertexLayout['uv'][1] = regReadDword('NR_VertexLayout_TCV')

    mdlscaler = regReadFloat('NR_TransformScale')
    g_ninjarotX = regReadFloat('NR_TransformRotateX')
    g_ninjarotY = regReadFloat('NR_TransformRotateY')
    g_ninjarotZ = regReadFloat('NR_TransformRotateZ')
    uvscaler = regReadFloat('NR_TransformUVScale')

    g_Tex0_FileLev = regReadDword('NR_MiscTextureNumber')
    g_flipUV = regReadDword('NR_MiscFlipUV')
    g_normalizeUV = regReadBool('NR_MiscNormalizeUV')

    # cmds.intField(
    #    'NR_VertexLayout_PosX', edit=True, v=VertexLayout['pos'][0]
    # )
    # cmds.intField(
    #    'NR_VertexLayout_PosY', edit=True, v=VertexLayout['pos'][1]
    # )
    # cmds.intField(
    #    'NR_VertexLayout_PosZ', edit=True, v=VertexLayout['pos'][2]
    # )

    cmds.intField('NR_VertexLayout_NmlX', edit=True, v=VertexLayout['nml'][0])
    cmds.intField('NR_VertexLayout_NmlY', edit=True, v=VertexLayout['nml'][1])
    cmds.intField('NR_VertexLayout_NmlZ', edit=True, v=VertexLayout['nml'][2])
    cmds.intField('NR_VertexLayout_TCU', edit=True, v=VertexLayout['uv'][0])
    cmds.intField('NR_VertexLayout_TCV', edit=True, v=VertexLayout['uv'][1])

    cmds.floatField('NR_TransformScale', edit=True, v=mdlscaler)
    cmds.floatField('NR_TransformRotateX', edit=True, v=g_ninjarotX)
    cmds.floatField('NR_TransformRotateY', edit=True, v=g_ninjarotY)
    cmds.floatField('NR_TransformRotateZ', edit=True, v=g_ninjarotZ)
    cmds.floatField('NR_TransformUVScale', edit=True, v=uvscaler)

    cmds.intField('NR_MiscTextureNumber', edit=True, v=g_Tex0_FileLev)
    cmds.checkBox(
        'NR_MiscFlipUV', edit=True, v=True if g_flipUV == -1 else False
    )

    cmds.checkBox('NR_MiscNormalizeUV', edit=True, v=g_normalizeUV)

    if g_VertexFormatRecog == 0:
        cmds.radioButton('NR_VertexRecognitionAuto', edit=True, sl=True)
        onAutoButtonPressed()
    else:
        cmds.radioButton('NR_VertexRecognitionManual', edit=True, sl=True)
        onManualButtonPressed()


def saveOptions():
    regSetDword("NR_VertexRecognition", g_VertexFormatRecog)
    regSetString("InitialDirectory", InitialDirectory)

    # regSetDword("NR_VertexLayout_PosX", VertexLayout['pos'][0])
    # regSetDword("NR_VertexLayout_PosY", VertexLayout['pos'][1])
    # regSetDword("NR_VertexLayout_PosZ", VertexLayout['pos'][2])

    regSetDword("NR_VertexLayout_NmlX", VertexLayout['nml'][0])
    regSetDword("NR_VertexLayout_NmlY", VertexLayout['nml'][1])
    regSetDword("NR_VertexLayout_NmlZ", VertexLayout['nml'][2])
    regSetDword("NR_VertexLayout_TCU", VertexLayout['uv'][0])
    regSetDword("NR_VertexLayout_TCV", VertexLayout['uv'][1])
    regSetFloat("NR_TransformScale", mdlscaler)
    regSetFloat("NR_TransformRotateX", g_ninjarotX)
    regSetFloat("NR_TransformRotateY", g_ninjarotY)
    regSetFloat("NR_TransformRotateZ", g_ninjarotZ)
    regSetFloat("NR_TransformUVScale", uvscaler)
    regSetDword("NR_MiscTextureNumber", g_Tex0_FileLev)
    regSetDword("NR_MiscFlipUV", g_flipUV)
    regSetBool("NR_MiscNormalizeUV", g_normalizeUV)


def setupRegister():
    global RegisterKey
    try:
        RegisterKey = reg.OpenKey(
            reg.HKEY_CURRENT_USER,
            "SOFTWARE\\Autodesk\\MayaPlugins\\NinjaRipperMayaImportTools"
        )
    except WindowsError:
        RegisterKey = reg.CreateKey(
            reg.HKEY_CURRENT_USER,
            "SOFTWARE\\Autodesk\\MayaPlugins\\NinjaRipperMayaImportTools"
        )
        regSetDword("NR_VertexRecognition", 0)
        regSetString("InitialDirectory", "")
        # regSetDword("NR_VertexLayout_PosX", 0)
        # regSetDword("NR_VertexLayout_PosY", 1)
        # regSetDword("NR_VertexLayout_PosZ", 2)
        regSetDword("NR_VertexLayout_NmlX", 3)
        regSetDword("NR_VertexLayout_NmlY", 4)
        regSetDword("NR_VertexLayout_NmlZ", 5)
        regSetDword("NR_VertexLayout_TCU", 6)
        regSetDword("NR_VertexLayout_TCV", 7)
        regSetFloat("NR_TransformScale", 100.0)
        regSetFloat("NR_TransformRotateX", 90.0)
        regSetFloat("NR_TransformRotateY", 0.0)
        regSetFloat("NR_TransformRotateZ", 0.0)
        regSetFloat("NR_TransformUVScale", 1.0)
        regSetDword("NR_MiscTextureNumber", 0)
        regSetDword("NR_MiscFlipUV", 0)
        regSetBool("NR_MiscNormalizeUV", False)


createMenu()
createImportWindow()
setupRegister()
loadOptions()
printMessage("NinjaRipperMayaImportTools loaded successfully!")
