# csstransformexport 

## What is it?

It's an exporter for [Blender 3D] [1], which exports any Blender scene to a HTML document which uses [CSS Transforms] [2] and [Animations] [3] to construct and animate the scene.

Scenes can either be exported in 2D or 3D. Currently the only objects supported are Empties and Planes.

## Why?

Using a text editor is far from the most intuitive method for making a complex animated scene using CSS Transforms and Animations. Simply put, this is intended to cut out the tedious and unfriendly editing process to let you get on with the important part: the actual content.

## How do i construct a scene for export?

Refer to the example blender files. Generally speaking you need to use Planes or Empties, laying out everything on the XY plane (top view). Each blender unit equals 1 pixel, which can be modified by altering the "Scale" factor.

## Which browsers are supported?

Currently only browsers based on Webkit are fully supported (i.e. Safari, MobileSafari, Chrome). Additionally there is limited support (excluding animations) for Firefox.

## Which versions of blender are supported?

Currently only Blender 2.49 is supported.

[1]: http://www.blender.org/
[2]: http://webkit.org/blog/130/css-transforms/
[3]: http://webkit.org/blog/138/css-animation/
