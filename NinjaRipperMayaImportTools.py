import maya.cmds as cmds
import maya.OpenMaya as OpenMaya
import maya.mel as mel
import struct
import os
import os.path
import unicodedata
import _winreg as reg

g_debugMessages = True

RipSignature = 0xDEADC0DE
RipFileVersion = 4

InitialDirectory = ""

# Global vars.
g_Tex0_FileLev = 0
ImportAnything = False

g_Mesh_Index = 0  # For renaming purposes.

VertexLayout = {
    'pos': [0, 1, 2, 3],  # Can be 2 of 4
    'nml': [4, 5, 6, 7],
    'uvw': [8, 9, 10, 11],  # Can be only 1 of 3. Met 4, but not in use.
    'posUpdated': False,
    'nmlUpdated': False,
    'uvwUpdated': False,
    'autoMode': True,
    'posCount': 0,
    'nmlCount': 0,
    'uvwCount': 0,
}

# Globals additional.
mdlscaler = 100
g_ninjarotX = 90
g_ninjarotY = 0
g_ninjarotZ = 0
uvscaler = 1

g_flipUV = 1
g_normalizeUV = False
g_reverseNormals = False

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


def printDebug(text):
    if g_debugMessages is True:
        print(text)


def printMessage(text):
    mel.eval("print \"[NR]: {}\\n\"".format(text))


def regReadFloat(keyName):
    return float(regReadString(keyName))


def regReadDword(keyName):
    result = 0
    try:
        result = reg.QueryValueEx(RegisterKey, keyName)[0]
    except WindowsError:
        result = 0
    return result


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
    return struct.unpack('<LLLLLLLL', f.read(32))


def updateVertexLayoutIndexes(t, baseIndex, count):
    if t is None:
        return

    global VertexLayout

    keyUpdated = "{}Updated".format(t)
    keyCount = "{}Count".format(t)
    # printDebug(keyUpdated)
    # printDebug(keyCount)
    if VertexLayout[keyUpdated] is False:
        for i in range(count):
            printDebug("VertexLayout[{}][{}]".format(t, i))
            VertexLayout[t][i] = baseIndex + i
        VertexLayout[keyUpdated] = True
        VertexLayout[keyCount] = count


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

        vertexAttributes.append([semantic, offset / 4, size / 4])

    if VertexLayout['autoMode'] is True:  # AUTO recognition.
        applyRecognitionLogic(vertexAttributes)

    return result


def applyRecognitionLogic(vertexAttributes):
    # vertexAttributes[i]:
    # [0] semantic
    # [1] index
    # [2] count

    shortNames = {'POSITION': 'pos', 'NORMAL': 'nml', 'TEXCOORD': 'uvw', 'SV_POSITION': 'pos'}

    printDebug("vertexAttributes Count: {}".format(len(vertexAttributes)))

    for i in range(len(vertexAttributes)):
        printDebug("vertexAttributes[{}] = {}, selected: {}".format(i, vertexAttributes[i], shortNames.get(vertexAttributes[i][0], None)))
        updateVertexLayoutIndexes(
            shortNames.get(vertexAttributes[i][0], None),
            vertexAttributes[i][1],
            vertexAttributes[i][2]
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
            faceArray.append(data[j])

    return faceArray


def generateVertexFromData(vertexData):
    arr = [0.0, 0.0, 0.0, 0.0]
    for i in range(VertexLayout['posCount']):  # Up to 4
        arr[i] = vertexData[VertexLayout['pos'][i]]
    return OpenMaya.MFloatPoint(arr[0], arr[1], arr[2], arr[3])


def generateNormalFromData(vertexData):
    result = []
    for i in range(VertexLayout['nmlCount']):  # Up to 4
        result.append(vertexData[VertexLayout['nml'][i]])
    return result


def generateTexCoordFromData(vertexData, offset):
    if VertexLayout['uvwCount'] > offset:
        return vertexData[VertexLayout['uvw'][offset]]
    return 0


def readRIPVertexes(f, count, vertDict):
    result = []

    Vert_array = OpenMaya.MFloatPointArray()
    Normal_array = []
    UArray = OpenMaya.MFloatArray()
    VArray = OpenMaya.MFloatArray()

    rawStructSize = len(vertDict) * 4
    for i in range(count):
        vertexData = struct.unpack(vertDict, f.read(rawStructSize))

        Vert_array.append(generateVertexFromData(vertexData))
        Normal_array.append(generateNormalFromData(vertexData))
        UArray.append(generateTexCoordFromData(vertexData, 0))
        VArray.append(1 - generateTexCoordFromData(vertexData, 1))

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
    is3DModel = VertexLayout['posCount'] >= 3 and VertexLayout['uvwCount'] == 2
    isFileReadOK = h[3] == v[0].length() and h[2] == f.length() / 3
    return (is3DModel or ImportAnything) and isFileReadOK


def importRip(path):
    global VertexLayout
    global mdlscaler
    global uvscaler
    global g_flipUV
    global g_Tex0_FileLev

    # Reset this in case of loading multiple meshes in auto mode.
    VertexLayout['posUpdated'] = False
    VertexLayout['posCount'] = 0
    VertexLayout['nmlUpdated'] = False
    VertexLayout['nmlCount'] = 0
    VertexLayout['uvwUpdated'] = False
    VertexLayout['uvwCount'] = 0

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

        # printDebug("*****ImportRip() File: " + path)
        # printDebug("dwFacesCnt=" + str(dwFacesCnt))
        # printDebug("dwVertexesCnt=" + str(dwVertexesCnt))
        # printDebug("VertexAttributesCnt=" + str(VertexAttributesCnt))

        # Read vertex attributes.
        vertexStructDictionary = readRIPVertexAttrib(f, header[7])
        # Read textures list (if present).
        TextureFiles = readRIPStrings(f, header[5])
        # Read shader list (if present).
        ShaderFiles = readRIPStrings(f, header[6])
        # Read mesh faces.
        Face_array = readRIPFaces(f, header[2])
        # Read vertexes data.
        VertexData = readRIPVertexes(f, header[3], vertexStructDictionary)
        # VertexData:
        # [0] - Vert_array
        # [1] - Normal_array
        # [2] - UArray
        # [3] - VArray

    printDebug("RIP info for '{}'".format(path))
    printDebug("VertexLayout['autoMode'] = {}".format(VertexLayout['autoMode']))
    printDebug("VertexLayout['pos'][0] = {}".format(VertexLayout['pos'][0]))
    printDebug("VertexLayout['pos'][1] = {}".format(VertexLayout['pos'][1]))
    printDebug("VertexLayout['pos'][2] = {}".format(VertexLayout['pos'][2]))
    printDebug("VertexLayout['nml'][0] = {}".format(VertexLayout['nml'][0]))
    printDebug("VertexLayout['nml'][1] = {}".format(VertexLayout['nml'][1]))
    printDebug("VertexLayout['nml'][2] = {}".format(VertexLayout['nml'][2]))
    printDebug("VertexLayout['uvw'][0] = {}".format(VertexLayout['uvw'][0]))
    printDebug("VertexLayout['uvw'][1] = {}".format(VertexLayout['uvw'][1]))
    printDebug("VertexLayout['uvw'][2] = {}".format(VertexLayout['uvw'][2]))
    printDebug("mdlscaler = {}".format(mdlscaler))
    printDebug("uvscaler = {}".format(uvscaler))
    printDebug("g_Tex0_FileLev = {}".format(g_Tex0_FileLev))
    printDebug("g_flipUV = {}".format(g_flipUV))
    printDebug("VertexLayout['posCount'] = {}".format(VertexLayout['posCount']))
    printDebug("VertexLayout['nmlCount'] = {}".format(VertexLayout['nmlCount']))
    printDebug("VertexLayout['uvwCount'] = {}".format(VertexLayout['uvwCount']))

    textureFile = "setka.png"
    if TextureFiles:
        textureFile = TextureFiles[g_Tex0_FileLev]

    if isFileReadCorrect(header, VertexData, Face_array):
        ImportToMaya(
            VertexData[0], Face_array, [VertexData[2], VertexData[3]],
            os.path.dirname(path), textureFile
        )
        return

    printMessage(
        "File reading error: incomplete vertex/faces arrays " +
        "or file not a 3D object. Use ripdump.exe if you want to " + 
        "get more information."
    )


def ImportToMaya(vertexArray, polygonConnects, uvArray, texturePath, texture):
    global g_Mesh_Index

    printMessage("Creating mesh...")
    polygonCounts = OpenMaya.MIntArray(polygonConnects.length() / 3, 3)
    mesh = OpenMaya.MFnMesh()
    transform = mesh.create(
        vertexArray.length(), polygonCounts.length(), vertexArray,
        polygonCounts, polygonConnects
    )

    printDebug("connects cnt {}".format(polygonConnects.length()))
    printDebug("cnt {}".format(polygonCounts.length()))
    printDebug("u cnt {}".format(uvArray[0].length()))
    printDebug("v cnt {}".format(uvArray[1].length()))

    # UV map.
    printMessage("Mapping UVs...")
    mesh.setUVs(uvArray[0], uvArray[1])

    try:
        mesh.assignUVs(polygonCounts, polygonConnects)
    except RuntimeError:
        printDebug("mesh.assignUVs() failed. Assign manually...")
        for i in range(0, polygonConnects.length()):
            try:
                mesh.assignUV(i / 3, i % 3, polygonConnects[i])
            except RuntimeError:
                printMessage("AssignUV failed: " + 
                            "[{}] = {}".format(i, polygonConnects[i]))

    # Rename mesh.
    printMessage("Renaming mesh...")
    transformDagPath = OpenMaya.MDagPath()
    OpenMaya.MDagPath.getAPathTo(transform, transformDagPath)
    meshName = cmds.rename(
        transformDagPath.fullPathName(), "NinjaMesh_{}".format(g_Mesh_Index)
    )
    g_Mesh_Index = g_Mesh_Index + 1

    # Apply textures.
    printMessage("Applying textures...")
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
    printMessage("Forcing vertex color to white...")
    cmds.select(meshName)
    cmds.polyColorPerVertex(cdo=True, rgb=[1, 1, 1])

    # Apply transformations.
    printMessage("Applying transformations...")
    cmds.setAttr("{}.rotateX".format(meshName), g_ninjarotX)
    cmds.setAttr("{}.rotateY".format(meshName), g_ninjarotY)
    cmds.setAttr("{}.rotateZ".format(meshName), g_ninjarotZ)
    cmds.setAttr("{}.scaleX".format(meshName), mdlscaler)
    cmds.setAttr("{}.scaleY".format(meshName), mdlscaler)
    cmds.setAttr("{}.scaleZ".format(meshName), mdlscaler)

    # Freeze transformations.
    printMessage("Zeroing new transform values...")
    cmds.makeIdentity(apply=True, t=1, r=1, s=1, n=0, pn=1)

    # Scale UVs.
    printMessage("Scaling UVs...")
    uvs = cmds.polyListComponentConversion(meshName, tuv=True)
    cmds.select(uvs)
    cmds.polyEditUV(su=uvscaler, sv=uvscaler*g_flipUV)

    # Normalize UV.
    if g_normalizeUV:
        printMessage("Normalizing UVs...")
        cmds.polyNormalizeUV(nt=1, pa=True, centerOnTile=True)

    # Merge duplicates.
    printMessage("Removing duplicate vertex...")
    cmds.select(cl=True)
    cmds.select(meshName)
    cmds.polyMergeVertex(d=0.01, am=True, ch=1)
    cmds.polyMergeUV(d=0.01, ch=True)

    # Reverse normals (First met in MWR)
    if g_reverseNormals:
        printMessage("Reversing normals...")
        cmds.select(cl=True)
        cmds.select(meshName)
        cmds.polyNormal(meshName, ch=1)

    cmds.select(cl=True)
    print("Import done for mesh '{}'".format(meshName))


def changeVertexRecognition(isManual):
    global VertexLayout
    VertexLayout['autoMode'] = isManual is False
    cmds.frameLayout('NR_VertexLayout_Position', edit=True, en=False)
    cmds.frameLayout('NR_VertexLayout_Normal', edit=True, en=isManual)
    cmds.frameLayout('NR_VertexLayout_TexCoord', edit=True, en=isManual)


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
    global g_reverseNormals
    global ImportAnything

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
    g_reverseNormals = cmds.checkBox('NR_MiscReverseNormals', query=True, v=True)
    ImportAnything = cmds.checkBox('NR_MiscImportAnything', query=True, v=True)

    if VertexLayout['autoMode'] is False:
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
        VertexLayout['uvw'][0] = cmds.intField(
            'NR_VertexLayout_TCU', query=True, v=True
        )
        VertexLayout['uvw'][1] = cmds.intField(
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
    cmds.checkBox(
        'NR_MiscReverseNormals', label="Reverse normals",
        ann="Reverse normals"
    )
    cmds.checkBox(
        'NR_MiscImportAnything', label='Import anything',
        ann='Do not ignore non-3D objects(incomplete pos/nml/uv coords)'
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
    global VertexLayout
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
    global g_reverseNormals
    global ImportAnything

    VertexLayout['autoMode'] = regReadBool('NR_AutoMode')
    InitialDirectory = regReadString('InitialDirectory')

    # VertexLayout['pos'][0] = regReadDword('NR_VertexLayout_PosX')
    # VertexLayout['pos'][2] = regReadDword('NR_VertexLayout_PosY')
    # VertexLayout['pos'][3] = regReadDword('NR_VertexLayout_PosZ')

    VertexLayout['nml'][0] = regReadDword('NR_VertexLayout_NmlX')
    VertexLayout['nml'][1] = regReadDword('NR_VertexLayout_NmlY')
    VertexLayout['nml'][2] = regReadDword('NR_VertexLayout_NmlZ')
    VertexLayout['uvw'][0] = regReadDword('NR_VertexLayout_TCU')
    VertexLayout['uvw'][1] = regReadDword('NR_VertexLayout_TCV')

    mdlscaler = regReadFloat('NR_TransformScale')
    g_ninjarotX = regReadFloat('NR_TransformRotateX')
    g_ninjarotY = regReadFloat('NR_TransformRotateY')
    g_ninjarotZ = regReadFloat('NR_TransformRotateZ')
    uvscaler = regReadFloat('NR_TransformUVScale')

    g_Tex0_FileLev = regReadDword('NR_MiscTextureNumber')
    g_flipUV = regReadDword('NR_MiscFlipUV')
    g_normalizeUV = regReadBool('NR_MiscNormalizeUV')
    g_reverseNormals = regReadBool('NR_MiscReverseNormals')

    ImportAnything = regReadBool('NR_MiscImportAnything')

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
    cmds.intField('NR_VertexLayout_TCU', edit=True, v=VertexLayout['uvw'][0])
    cmds.intField('NR_VertexLayout_TCV', edit=True, v=VertexLayout['uvw'][1])

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
    cmds.checkBox('NR_MiscReverseNormals', edit=True, v=g_reverseNormals)
    cmds.checkBox('NR_MiscImportAnything', edit=True, v=ImportAnything)

    if VertexLayout['autoMode'] is True:
        cmds.radioButton('NR_VertexRecognitionAuto', edit=True, sl=True)
        changeVertexRecognition(False)
    else:
        cmds.radioButton('NR_VertexRecognitionManual', edit=True, sl=True)
        changeVertexRecognition(True)


def saveOptions():
    regSetBool("NR_AutoMode", VertexLayout['autoMode'])
    regSetString("InitialDirectory", InitialDirectory)

    # regSetDword("NR_VertexLayout_PosX", VertexLayout['pos'][0])
    # regSetDword("NR_VertexLayout_PosY", VertexLayout['pos'][1])
    # regSetDword("NR_VertexLayout_PosZ", VertexLayout['pos'][2])

    regSetDword("NR_VertexLayout_NmlX", VertexLayout['nml'][0])
    regSetDword("NR_VertexLayout_NmlY", VertexLayout['nml'][1])
    regSetDword("NR_VertexLayout_NmlZ", VertexLayout['nml'][2])
    regSetDword("NR_VertexLayout_TCU", VertexLayout['uvw'][0])
    regSetDword("NR_VertexLayout_TCV", VertexLayout['uvw'][1])
    regSetFloat("NR_TransformScale", mdlscaler)
    regSetFloat("NR_TransformRotateX", g_ninjarotX)
    regSetFloat("NR_TransformRotateY", g_ninjarotY)
    regSetFloat("NR_TransformRotateZ", g_ninjarotZ)
    regSetFloat("NR_TransformUVScale", uvscaler)
    regSetDword("NR_MiscTextureNumber", g_Tex0_FileLev)
    regSetDword("NR_MiscFlipUV", g_flipUV)
    regSetBool("NR_MiscNormalizeUV", g_normalizeUV)
    regSetBool("NR_MiscReverseNormals", g_reverseNormals)
    regSetBool('NR_MiscImportAnything', ImportAnything)


def setupRegister():
    global RegisterKey
    try:
        RegisterKey = reg.OpenKey(
            reg.HKEY_CURRENT_USER,
            "SOFTWARE\\Autodesk\\MayaPlugins\\NinjaRipperMayaImportTools",
            0,
            reg.KEY_ALL_ACCESS
        )
    except WindowsError:
        RegisterKey = reg.CreateKey(
            reg.HKEY_CURRENT_USER,
            "SOFTWARE\\Autodesk\\MayaPlugins\\NinjaRipperMayaImportTools"
        )
        regSetBool("NR_AutoMode", True)
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
        regSetBool("NR_MiscReverseNormals", False)
        regSetBool('NR_MiscImportAnything', False)


createMenu()
createImportWindow()
setupRegister()
loadOptions()
printMessage("NinjaRipperMayaImportTools loaded successfully!")
