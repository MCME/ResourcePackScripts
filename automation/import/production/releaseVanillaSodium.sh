#!/bin/bash

# $1 RP Name
# $2 GitHub Owner
# $3 GitHub Repository
# $4 Version tag
# $5 Release name

echo compiling $1 RP zips
echo $1-Sodium
cd $1-Sodium
git pull
cd ..
cd ResourcePackScripts
git pull
cd ..

rm -r release
mkdir release
cp -f -r $1-Sodium/* release 

cd release
7z a -y $1-Sodium.zip '-x!vanilla' '-x!.git'
#packsquash packsquash.toml
mv  $1-Sodium.zip ..
cd ..

echo $1-Sodium-Footprints
cp -f Footprints/activator_rail.png release/assets/minecraft/textures/block/activator_rail.png

cd release
7z a -y $1-Sodium-Footprints.zip '-x!vanilla' '-x!.git'
mv -f $1-Sodium-Footprints.zip ..
cd ..

echo $1-Vanilla
rm -r release
mkdir release

python3 ResourcePackScripts/generateVanilla/generateVanilla.py $1-Sodium release Vanilla-26.2 --objmc ResourcePackScripts/generateVanilla/objmc.py

cd release
7z a -y $1-Vanilla.zip *
mv  $1-Vanilla.zip ..
cd ..

echo $1-Vanilla-Footprints
cp -f Footprints/activator_rail.png release/assets/minecraft/textures/block/activator_rail.png
cp -f Footprints/activator_rail_on.png release/assets/minecraft/textures/block/activator_rail_on.png

cd release
7z a -y $1-Vanilla-Footprints.zip *
mv -f $1-Vanilla-Footprints.zip ..
cd ..

echo $1-Lite
rm -r release
mkdir release

python3 ResourcePackScripts/generateVanilla/generateVanilla.py $1-Sodium release Vanilla-26.2 --objmc ResourcePackScripts/generateVanilla/objmc.py --limit 2

cd release
7z a -y $1-Lite.zip *
mv  $1-Lite.zip ..
cd ..

echo $1-Lite-Footprints
cp -f Footprints/activator_rail.png release/assets/minecraft/textures/block/activator_rail.png
cp -f Footprints/activator_rail_on.png release/assets/minecraft/textures/block/activator_rail_on.png

cd release
7z a -y $1-Lite-Footprints.zip *
mv -f $1-Lite-Footprints.zip ..
cd ..

echo releasing $1 RP zips

gh release create $4 -R $2/$3 -t "$5" -n "Version $4 for MC 1.21.4"
gh release upload $4 $1-Vanilla.zip $1-Vanilla-Footprints.zip $1-Sodium.zip $1-Sodium-Footprints.zip $1-Lite.zip $1-Lite-Footprints.zip -R $2/$3 --clobber
