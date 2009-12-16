"""
Name: 'CSS Transform Export (.html)'
Blender: 249
Group: 'Export'
Tooltip: 'Export to a webkit-compatible HTML document.'
"""

"""
Copyright (C) 2009 James S Urquhart (contact@jamesu.net)

This program is free software; you can redistribute it and/or modify it 
under the terms of the GNU General Public License as published by the 
Free Software Foundation; either version 2 of the License, 
or (at your option) any later version.

This program is distributed in the hope that it will be useful, 
but WITHOUT ANY WARRANTY; without even the implied warranty of 
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. 
See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License 
along with this program; if not, write to the 
Free Software Foundation, Inc., 59 Temple Place, 
Suite 330, Boston, MA 02111-1307 USA
"""

import Blender
import math
import string

from Blender import Draw

CONFIG = {
	'ANIM_LOOP': True,             # Animations loop
	'ANIM_BAKE': True,             # Sample animation each frame (interpolation will be forced to linear)
	'EXPORT_3D' : False,           # Incorporates Z axis and camera perspective
	'SWITCH_AXIS' : False,         # Switch Z and Y axes (useful if incoporating simulated physics)
	'COLLAPSE_TRANSFORMS' : False, # Use world space transforms instead of relying on parent-child transforms. Buggy with anims.
	'FPS': None                    # Override FPS
}

# NOTE: Keyframes only interpolate between individual keys, i.e. values don't
#       interpolate across the entire animation.

# BEGIN TEMPLATES

WEBKIT_TPL = """
<html>
<head>
<title>%(title)s</title>
<style>%(style)s</style>
</head>
<body>
<div id=\"root\">%(scene)s</div>
</body>
"""

# END TEMPLATES

# Lookups

InterpolationLookup = {
	Blender.IpoCurve.InterpTypes.CONST:"linear",
	Blender.IpoCurve.InterpTypes.LINEAR:"linear",
	Blender.IpoCurve.InterpTypes.BEZIER:"bezier"
}

# Util

import os.path

# Gets the Base Name from the File Path
def basename(filepath):
	if "\\" in filepath:
		words = string.split(filepath, "\\")
	else:
		words = string.split(filepath, "/")
	words = string.split(words[-1], ".")
	return string.join(words[0:len(words)], ".")
 
# Gets base path with trailing /
def basepath(filepath):
	if "\\" in filepath: sep = "\\"
	else: sep = "/"
	words = string.split(filepath, sep)
	# join drops last word (file name)
	return string.join(words[:-1], sep)
 
# Gets the Base Name & path from the File Path
def noext(filepath):
	words = string.split(filepath, ".")
	if len(words)==1: return filepath
	return string.join(words[:-1], ".")

class Bitfield:
	INT_WIDTH=32
	
	def __init__(self, size):
		self.size = int(size)
		self.field = [0] * int(math.ceil(float(self.size) / Bitfield.INT_WIDTH))
	
	def __setitem__(self, position, value):
		if value:
			self.field[position / Bitfield.INT_WIDTH] |= 1 << (position % Bitfield.INT_WIDTH)
		elif self.field[position / Bitfield.INT_WIDTH] & 1 << (position % Bitfield.INT_WIDTH) > 0:
			self.field[position / Bitfield.INT_WIDTH] ^= 1 << (position % Bitfield.INT_WIDTH)
	
	def __getitem__(self, position):
		try:
			if self.field[position / Bitfield.INT_WIDTH] & 1 << (position % Bitfield.INT_WIDTH) > 0:
				return 1
			else:
				return 0
		except:
			return 0
	
	def dump(self):
		out = []
		for item in self.field:
			st = map(lambda y:str((item>>y)&1), range(Bitfield.INT_WIDTH-1, -1, -1))
			st.reverse()
			out.append("".join(st))
		return (''.join(out))
		
	# e.g. [0,0,1,1,0,0].setFrom([1,1,1,1,1,1], -6) == [1,1,1,1,1,1,0,0,1,1,0,0]
	def setFrom(self, other, offset):
		pos = other.size + offset
		new_size = self.size
		start_pos = 0
		if pos > new_size:
			# Expand
			new_size = pos
		if offset < 0:
			new_size += -offset
			start_pos = -offset
		
		new_field = Bitfield(new_size)
		# Copy existing
		for i in range(start_pos, start_pos+self.size):
			new_field[i] = self[i-start_pos]
		# Copy new
		for i in range(offset, offset+other.size):
			if not new_field[i]:
				new_field[i] = other[i-offset]
		return new_field

# Helper class for CSS transforms
class SimpleTransform:
	MATTERS_LOCX=1<<0
	MATTERS_LOCY=1<<1
	MATTERS_LOCZ=1<<2
	
	MATTERS_LOC2D = MATTERS_LOCX | MATTERS_LOCY
	MATTERS_LOC3D = MATTERS_LOCX | MATTERS_LOCY | MATTERS_LOCZ
	
	MATTERS_ROTX=1<<3
	MATTERS_ROTY=1<<4
	MATTERS_ROTZ=1<<5
	
	MATTERS_ROT3D = MATTERS_ROTX | MATTERS_ROTY | MATTERS_ROTZ
	
	MATTERS_SCLX=1<<6
	MATTERS_SCLY=1<<7
	MATTERS_SCLZ=1<<8
	
	MATTERS_SCL2D = MATTERS_SCLX | MATTERS_SCLY
	MATTERS_SCL3D = MATTERS_SCLX | MATTERS_SCLY | MATTERS_SCLZ
	
	# Global scaling
	GLOBAL_SCALE = 10.0
	
	def __init__(self):
		self.matters = 0
		self.loc = [0,0,0]
		self.rot = [0,0,0]
		self.scl = [0,0,0]
		
		self.is3D = False
	
	def setLocation(self, x, y, z):
		if x != None and x != self.loc[0]:
			self.matters |= SimpleTransform.MATTERS_LOCX
			self.loc[0] = x
		if y != None and y != self.loc[1]:
			self.matters |= SimpleTransform.MATTERS_LOCY
			self.loc[1] = y
		if z != None and z != self.loc[2]:
			self.matters |= SimpleTransform.MATTERS_LOCZ
			self.loc[2] = z
	
	def setRotation(self, x, y, z):
		if x != None and x != self.rot[0]:
			self.matters |= SimpleTransform.MATTERS_ROTX
			self.rot[0] = x
		if y != None and y != self.rot[1]:
			self.matters |= SimpleTransform.MATTERS_ROTY
			self.rot[1] = y
		if z != None and z != self.rot[2]:
			self.matters |= SimpleTransform.MATTERS_ROTZ
			self.rot[2] = z
	
	def setScale(self, x, y, z):
		if x != None and x != self.scl[0]:
			self.matters |= SimpleTransform.MATTERS_SCLX
			self.scl[0] = x
		if y != None and y != self.scl[1]:
			self.matters |= SimpleTransform.MATTERS_SCLY
			self.scl[1] = y
		if z != None and z != self.scl[2]:
			self.matters |= SimpleTransform.MATTERS_SCLZ
			self.scl[2] = z
	
	def transformValue(self):
		string = ""
		list = []
		
		# Location
		if CONFIG["EXPORT_3D"] and self.matters & SimpleTransform.MATTERS_LOC3D == SimpleTransform.MATTERS_LOC3D:
			list.append("translate3d(%fpx, %fpx, %fpx)" % (self.loc[0], self.loc[1], self.loc[2]))
		elif self.matters & SimpleTransform.MATTERS_LOC2D == SimpleTransform.MATTERS_LOC2D:
			list.append("translate(%fpx, %fpx)" % (self.loc[0], self.loc[1]))
		else:
			if self.matters & SimpleTransform.MATTERS_LOCX:
				list.append("translateX(%fpx)" % self.loc[0])
			if self.matters & SimpleTransform.MATTERS_LOCY:
				list.append("translateY(%fpx)" % self.loc[1])
			if CONFIG["EXPORT_3D"] and self.matters & SimpleTransform.MATTERS_LOCZ:
				list.append("translateZ(%fpx)" % self.loc[2])
		
		# Rotation
		# TODO: rotate3d()
		if CONFIG["EXPORT_3D"]:
			if self.matters & SimpleTransform.MATTERS_ROTX:
				list.append("rotateX(%fdeg)" % -self.rot[0])
			if self.matters & SimpleTransform.MATTERS_ROTY:
				list.append("rotateY(%fdeg)" % -self.rot[1])
			if self.matters & SimpleTransform.MATTERS_ROTZ:
				list.append("rotateZ(%fdeg)" % -self.rot[2])
		else:
			if self.matters & SimpleTransform.MATTERS_ROTZ:
				list.append("rotate(%fdeg)" % -self.rot[2])
		
		# Scale
		if CONFIG["EXPORT_3D"] and self.matters & SimpleTransform.MATTERS_SCL3D == SimpleTransform.MATTERS_SCL3D:
			list.append("scale3d(%f, %f, %f)" % (self.scl[0], self.scl[1], self.scl[2]))
		elif self.matters & SimpleTransform.MATTERS_SCL2D == SimpleTransform.MATTERS_SCL2D:
			list.append("scale(%f, %f)" % (self.scl[0], self.scl[1]))
		else:
			if self.matters & SimpleTransform.MATTERS_SCLX:
				list.append("scaleX(%f)" % self.scl[0])
			if self.matters & SimpleTransform.MATTERS_SCLY:
				list.append("scaleY(%f)" % self.scl[1])
			if CONFIG["EXPORT_3D"] and self.matters & SimpleTransform.MATTERS_SCLZ:
				list.append("scaleZ(%f)" % self.scl[2])
		
		return " ".join(list)

def scaleVA(arr, scale):
	return [x*scale for x in arr]
	
class SimpleObject:
	def __init__(self, obj):
		self.name = obj.name.replace(".", "__")
		self.obj = obj
		self.parent = None
		self.children = []
		self.anim = None
		self.material = None
		self.transformOrigin = None
		
		self.mesh = obj.getData(mesh=1)
		if self.mesh != None:
			mat_list = self.mesh.materials
			if len(mat_list) > 0:
				self.material = mat_list[0]
		
	def importIpo(self, ipo):
		anim = SimpleAnim(self)
		anim.grabAllFrameTimes()
		self.anim = anim
		return anim
	
	def blenderChildren(self):
		return [obj for obj in Blender.Object.Get() if obj.parent == self.obj ]
	
	def getTransform(self):
		mat = self.obj.getMatrix("localspace")
		# Handle collapsed transforms
		if CONFIG["COLLAPSE_TRANSFORMS"]:
			mat = self.obj.getMatrix("worldspace")
			#mat = parentMat * mat
		
		loc = scaleVA(mat.translationPart(), SimpleTransform.GLOBAL_SCALE)
		rot = mat.rotationPart().toEuler()
		scl = mat.scalePart()
		
		trans = SimpleTransform()
		
		if CONFIG["SWITCH_AXIS"]:
			trans.setLocation(loc[0], -loc[2], loc[1])
			trans.setRotation(rot[0], rot[2], rot[1])
			trans.setScale(scl[0], scl[2], scl[1])
		else:
			trans.setLocation(loc[0], -loc[1], loc[2])
			trans.setRotation(rot[0], rot[1], rot[2])
			trans.setScale(scl[0], scl[1], scl[2])
		
		return trans
	
	def getUVBounds(self):
		msh = self.mesh
		if msh != None and msh.faceUV:
			minp = [10e30,10e30]
			maxp = [-10e30,-10e30]
			
			uvcoords = []
			for f in msh.faces:
				for uv in f.uv:
					uvcoords.append(uv)
			for pos in uvcoords:
				for i in range(0,2):
					if pos[i] < minp[i]:
						minp[i] = pos[i]
					if pos[i] > maxp[i]:
						maxp[i] = pos[i]
			return minp, maxp

		return [0.0, 0.0], [1.0, 1.0]
	
	def getBounds(self):
		msh = self.mesh
		if msh != None:
			minp = [10e30,10e30,10e30]
			maxp = [-10e30,-10e30,-10e30]
			
			for v in msh.verts:
				pos = v.co
				for i in range(0,3):
					if pos[i] < minp[i]:
						minp[i] = pos[i]
					if pos[i] > maxp[i]:
						maxp[i] = pos[i]
			return scaleVA(minp, SimpleTransform.GLOBAL_SCALE), scaleVA(maxp, SimpleTransform.GLOBAL_SCALE)

		box = obj.getBoundBox()
		return scaleVA(min(box), SimpleTransform.GLOBAL_SCALE), scaleVA(max(box), SimpleTransform.GLOBAL_SCALE)
	
	def getWorldCenter(self):
		if self.parent != None:
			center = self.parent.getWorldCenter()
		else:
			center = [0,0,0]
		center[0] += self.center[0]
		center[1] += self.center[1]
		center[2] += self.center[2]
		return center

class SimpleAnim:
	def __init__(self, obj):
		self.object = obj
		self.identifier = obj.name + '-anim'
		self.matters = None
		self.frames = None # generated frames
		self.propertyInterpolation = {}
		self.start = 0
		self.len = 0
	
	def encompassesFrame(self, fid):
		if fid >= self.start and fid < self.start+self.len:
			return True
		return False
	
	def setPropertyInterpolationTypes(self):
		ipo = self.object.obj.ipo
		curve = ipo.curves[Blender.Ipo.OB_LOCX]
		if curve != None:
			self.propertyInterpolation["TRANSFORM"] = curve.interpolation
	
	def combineFrom(self, other):
		#print "COMBINING %s with %s" % (self.identifier, other.identifier)
		self.matters = self.matters.setFrom(other.matters, 0)
		
		# Fit start,len
		if other.start < self.start:
			self.len += self.start - other.start
			self.start = other.start
		sEnd = self.start + self.len
		oEnd = other.start + other.len
		if oEnd > sEnd:
			self.len += oEnd - sEnd
		
		for key in other.propertyInterpolation.keys():
			if not key in self.propertyInterpolation.keys():
				self.propertyInterpolation[key] = other.propertyInterpolation[key]
	
	def grabAllFrameTimes(self):
		ipo = self.object.obj.ipo
		frames = {}
		
		checkList = [Blender.Ipo.OB_LOCX, Blender.Ipo.OB_LOCY, Blender.Ipo.OB_LOCZ,
		             Blender.Ipo.OB_SCALEX, Blender.Ipo.OB_SCALEY, Blender.Ipo.OB_SCALEZ,
		             Blender.Ipo.OB_ROTX, Blender.Ipo.OB_ROTY, Blender.Ipo.OB_ROTZ]
		# TODO: incorporate ipo from linked material
		
		#print "ANIM: %s" % self.identifier
		curveFrameList = []
		for curve in checkList:
			try:
				cobj = ipo.curves[curve]
			except:
				continue
			curveFrames = self.getFrameTimes(ipo.curves[curve])
			if curveFrames != None:
				curveFrameList.append(curveFrames)
		
		# Combine all
		earliest, latest = self.getFrameTimeBounds(curveFrameList)  # e.g. 1, 2
		numFrames = ((latest+1) - earliest) # e.g. 1, 2 == 2
		
		for frameList in curveFrameList:
			self.combineFrameTimes(frameList, earliest, latest, frames)
		
		framesList = frames.values()
		framesList.sort(lambda a,b:cmp(a[0], b[0]))
		
		self.matters = Bitfield(latest+1)
		for frame in framesList:
			self.matters[frame[0]] = 1 # NOTE: frame 0 will be ignored
		
		#print "\tSTART=%i,END=%d,LEN=%d" % (earliest, latest, numFrames)
		self.start = earliest    # e.g. 1
		self.len = numFrames     # e.g. 2 [1,2]
		self.setPropertyInterpolationTypes()
	
	def combineFrameTimes(self, frames, startFrame, endFrame, outList):
		fl = endFrame - startFrame
		for frame in frames["frames"]:
			percent = float(frame[0]-startFrame) / fl  # e.g. 1-1 / 2-1 == 0; 2-1 / 2-1 == 1.0
			key = ("%2.2f" % (percent*100)) + "%"
			if not key in outList:
				outList[key] = [int(frame[0]), None]
	
	def getFrameTimes(self, curve):
		if curve == None:
			return None
		
		fr = map(lambda f: [f.pt[0], curve[f.pt[0]]], curve.bezierPoints)
		num = fr[-1][0] - fr[0][0]
		return {"frames":fr, 
				"start": fr[0][0],
				"end": fr[-1][0]}
	
	# Calculates overall start & stop time
	def getFrameTimeBounds(self, list):
		earliest = 99999999
		latest = -1
		
		for f in list:
			if f["start"] < earliest:
				earliest = f["start"]
			if f["end"] > latest:
				latest = f["end"]
			
		return earliest, latest

def importObjects(list, out_list, anims_list, parent=None):
	for obj in list:
		obj_parent = obj.getParent()
		if (parent == None and obj_parent != None) or (parent != None and obj_parent != parent.obj):
			continue
		
		if obj.getType() != "Mesh" and obj.getType() != "Empty":
			continue
		
		print obj.name
		
		ipo = obj.getIpo()
		built_object = SimpleObject(obj)
		
		if ipo != None:
			anims_list.append(built_object.importIpo(ipo))
		
		# Insert into correct list
		if parent != None:
			built_object.parent = parent
			parent.children.append(built_object)
		else:
			out_list.append(built_object)
		
		# Recurse
		importObjects(built_object.blenderChildren(), out_list, anims_list, built_object)

def halfOf(p1, p2):
	x = (p2[0] - p1[0]) * 0.5
	y = (p2[1] - p1[1]) * 0.5
	z = (p2[2] - p1[2]) * 0.5
	return [x, y, z]
	
def exportObjects(list, doc, style):
	for obj in list:
		# Actual div
		doc.append("<div id=\"%s\">" % obj.name)
		
		# CSS
		style.append("#%s {\n" % obj.name)
		
		if obj.mesh != None:
			minb, maxb = obj.getBounds()
			
			# Problem: we need to fix the origin of the HTML element. 
			#          -webkit-transform-origin only works for rotation and scaling.
			# Solution:
			#          use left and top to offset element center instead,
			#          taking into account the origin is by default at the center
			# e.g. bound size = 64,64
			#      bound origin = 0,0
			#      webkit origin = 32,32
			#      left, top = -32, -32  (i.e. bound origin - webkit origin)
			halfSize = halfOf(minb, maxb)
			
			boundOrigin = [
			halfSize[0] + minb[0],
			halfSize[1] + minb[1],
			halfSize[2] + minb[2]]
			
			boundOrigin[1] = -boundOrigin[1] # scene is -y
			
			obj.center = [
			boundOrigin[0] - halfSize[0],
			boundOrigin[1] - halfSize[1],
			boundOrigin[2] - halfSize[2]]
			
			# transformOrigin to correct rotation and scaling
			obj.transformOrigin = [-obj.center[0], -obj.center[1]]
		else:
			obj.center = [0,0,0]
		
		#print "%s actual center=%s" % (obj.obj.getName(), str(obj.center))
		
		if not CONFIG["COLLAPSE_TRANSFORMS"] and obj.parent != None:
			wc = obj.getWorldCenter()
			wc[0] -= obj.center[0]
			wc[1] -= obj.center[1]
			
			# Center needs to be expressed in parents coordinate system
			obj.center[0] = obj.center[0] - wc[0]
			obj.center[1] = obj.center[1] - wc[1]
		#
		#print "%s center=%s" % (obj.obj.getName(), str(obj.center))
		
		style.append("-webkit-transform: %s;\n" % obj.getTransform().transformValue())
		style.append("-moz-transform: %s;\n" % obj.getTransform().transformValue())
		
		if obj.mesh != None:
			style.append("width: %dpx;\n" % (maxb[0] - minb[0]))
			style.append("height: %dpx;\n" % (maxb[1] - minb[1]))
		style.append("left: %dpx;\n" % (obj.center[0]))
		style.append("top: %dpx;\n" % (obj.center[1]))
		if obj.transformOrigin != None:
			style.append("-webkit-transform-origin: %dpx %dpx;\n" % (obj.transformOrigin[0], obj.transformOrigin[1]))
			style.append("-moz-transform-origin: %dpx %dpx;\n" % (obj.transformOrigin[0], obj.transformOrigin[1]))
		
		if CONFIG["EXPORT_3D"]:
			style.append("-webkit-transform-style: preserve-3d;\n")
		
		# color, texture, etc
		if obj.material != None:
			# 
			mat = obj.material
			if not mat.mode & Blender.Material.Modes.TEXFACE:
				# color
				style.append("background-color: rgb(%d,%d,%d);\n" % (mat.R * 255, mat.G * 255, mat.B * 255))
				
			if mat.alpha < 1.0:
				style.append("opacity: %f;\n" % mat.alpha)
			
			# Use first texture slot to determine image background
			texSlot = mat.getTextures()[0]
			if texSlot != None:
				tex = texSlot.tex
				if tex != None:
					# Dump & save
					img = tex.getImage()
					if img != None:
						# Image file
						name = img.getFilename()
						style.append("background-image: url(\"%s.png\");\n" % noext(name))
						
						# Background position
						uv_min, uv_max = obj.getUVBounds()
						style.append("background-position: %i%% %i%%;\n" % (uv_min[0] * 100, uv_min[1] * 100))
						
						# Background scaling
						scale = [uv_max[0] - uv_min[0], 
						         uv_max[1] - uv_min[1]]
						
						# Calculate difference in image scale
						sz = img.getSize()
						oWidth = sz[0] / (maxb[0] - minb[0])
						oHeight = sz[1] / (maxb[1] - minb[1])
						
						scale[0] = round(scale[0] * 100, 2)
						scale[1] = round(scale[1] * 100, 2)
						
						if oWidth != 1.0 or oHeight != 1.0:
							style.append("-webkit-background-size: %.2f%% %.2f%%;\n" % (scale[0], scale[1]))
							style.append("-moz-background-size: %.2f%% %.2f%%;\n" % (scale[0], scale[1]))
		
		# animation
		if obj.anim != None:
			anim = obj.anim
			
			duration = anim.len / CONFIG["FPS"]
			delay = (anim.start-1) / CONFIG["FPS"]
			
			style.append("-webkit-animation-name: %s;\n" % anim.identifier)
			style.append("-webkit-animation-duration: %fs;\n" % duration)
			style.append("-webkit-animation-delay: %fs;\n" % delay)
			
			if CONFIG["ANIM_LOOP"]:
				style.append("-webkit-animation-iteration-count: infinite;\n")
			if CONFIG["ANIM_BAKE"]:
				style.append("-webkit-animation-timing-function: linear;\n")
			
		style.append("}\n")
		
		# Children are part of element
		if not CONFIG["COLLAPSE_TRANSFORMS"]:
			exportObjects(obj.children, doc, style)
		
		doc.append("</div>\n")
		
		# Children are part of root
		if CONFIG["COLLAPSE_TRANSFORMS"]:
			exportObjects(obj.children, doc, style)

def exportWebkit(objects, anims):
	# Second step: output webkit stuff
	doc = []
	style = ["#root div {position: absolute;}\n",
	         "#root {background-color: #eeeeee; position: absolute; width:640px; height: 480px;"]
	
	# 3D Needs to have a perspective and origin
	# TODO: some form of logical calculation using a camera
	if CONFIG["EXPORT_3D"]:
		style.append("-webkit-perspective: %i; " % (70))
		style.append("-webkit-perspective-origin: center 240px;")
	style.append("}\n")
	
	exportObjects(objects, doc, style)
	
	className = noext(basename(Blender.Get("filename")))
	classPath = basepath(Blender.Get("filename"))
	doBake = CONFIG["ANIM_BAKE"]
	
	# Animation keyframes
	for anim in anims:
		style.append("@-webkit-keyframes %s {\n" % anim.identifier)
		
		earliest = anim.start
		fl = anim.len-1
		frames = anim.frames
		for frame in frames:
			# e.g. two frames 1 2
			# (1 - 1) / 2 = 0%
			# (2 - 1) / 2 = 100%
			percent = float(frame[0] - earliest) / fl
			fid = ("%2.2f" % (percent*100)) + "%"
			
			style.append("%s {\n" % fid)
			style.append("-webkit-transform: %s;\n" % frame[1].transformValue())
			if not doBake:
				style.append("-webkit-animation-timing-function: %s;\n" % InterpolationLookup[frame[2]])
			style.append("}\n")
		
		style.append("}\n")
	
	substitutions = {'title': className, 'style': "".join(style), 'scene': "".join(doc)}
	
	# Dump to document
	fs = open("%s/%s.html" % (classPath, className), "w")
	fs.write(WEBKIT_TPL % substitutions)
	fs.close()

# Recursively makes sure child elements have anim tracks (for collapsed transforms)
def recursiveAnimClone(obj, new_anims):
	parent = obj.parent
	if parent != None and parent.anim != None:
		if obj.anim == None:
			obj.anim = SimpleAnim(obj)
			obj.anim.matters = Bitfield(parent.anim.matters.size)
			new_anims.append(obj.anim)
		obj.anim.combineFrom(parent.anim)
	
	for child in obj.children:
		recursiveAnimClone(child, new_anims)

def process():
	scene = Blender.Scene.GetCurrent()
	timeLine = scene.getTimeLine()
	
	ctx = scene.getRenderingContext()
	if CONFIG["FPS"] == None:
		CONFIG["FPS"] = ctx.fps
	
	objects = []
	anims = []
	
	Blender.Set("curframe", 1)
	
	# Import objects and frame times
	importObjects(scene.objects, objects, anims)
	
	# Collapse transforms if neccesary
	if CONFIG["COLLAPSE_TRANSFORMS"]:
		new_anims = []
		for anim in anims:
			recursiveAnimClone(anim.object, new_anims)
		anims += new_anims
	
	# Clear anim frames
	for anim in anims:
		anim.frames = []
	
	doBake = CONFIG["ANIM_BAKE"]
	
	# Grab frames for all anims
	for fid in range(ctx.sFrame, ctx.eFrame):
		Blender.Set("curframe", fid)
		
		for anim in anims:
			if anim.matters[fid] or (doBake and anim.encompassesFrame(fid)):
				# TODO: grab material color, etc
				interpolation = anim.propertyInterpolation["TRANSFORM"]
				if doBake:
					interpolation = "linear"
				anim.frames.append([fid, anim.object.getTransform(), interpolation])
	
	exportWebkit(objects, anims)
	
	# Reset FPS
	CONFIG["FPS"] = None

def event(evt, val):
	if evt == Draw.ESCKEY:
		Draw.Exit()

export_button = None
threedee_button = None
		
def doExport(evt, val):
	return process()

def doToggle3D(evt, val):
	CONFIG["EXPORT_3D"] = val

def doToggleLoop(evt, val):
	CONFIG["ANIM_LOOP"] = val

def doUpdateScale(evt, val):
	SimpleTransform.GLOBAL_SCALE = val

def gui():
	desc = Draw.Label("Webkit Exporter", 10, 194, 300, 20)
	descAuthor = Draw.Label("(C)2009 James S Urquhart. Refer to the LICENSE file for details.", 10, 180, 500, 20)
	descGeom = Draw.Label("Geometry", 10, 140, 200, 20)
	descAnim = Draw.Label("Animation", 10, 80, 200, 20)
	
	export_button = Draw.PushButton("Export", 1, 10, 10, 100, 24, "Export", doExport)
	threedee_button = Draw.Toggle("3D", 2, 10, 110, 40, 24, CONFIG["EXPORT_3D"], "3D", doToggle3D)
	loop_button = Draw.Toggle("Loop", 5, 10, 50, 40, 24, CONFIG["ANIM_LOOP"], "Loop animation track", doToggleLoop)
	scale_button = Draw.Number('Scale: ', 1000, 60, 110, 120, 24, SimpleTransform.GLOBAL_SCALE, 0.0,10.0, 'Global scale', doUpdateScale, 0.1, 2)
			
if __name__ == "__main__":
	Draw.Register(gui, event, None)
