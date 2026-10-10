#!/bin/bash

# $1 RP Name
# $2 GitHub Owner
# $3 GitHub Repository
# $4 Version tag
# $5 Release name

echo compiling $1 RP zips
cd $1-Vanilla
git pull
cd ..

rm -r release
mkdir release
cp -f -r $1-Vanilla/* release 
#packsquash packsquash.toml

cd release
7z a -y $1.zip * -x!inventories
mv  $1.zip ..
cd ..

cp -f Footprints/activator_rail.png release/assets/minecraft/textures/block/activator_rail.png
cp -f Footprints/activator_rail_on.png release/assets/minecraft/textures/block/activator_rail_on.png

cd release
7z a -y $1-Footprints.zip *  -x!inventories
mv -f $1-Footprints.zip ..
cd ..


echo releasing $1 RP zips

gh release create $4 -R $2/$3 -t "$5" -n "Version $4 for MC 1.21.4"
gh release upload $4 $1.zip $1-Footprints.zip -R $2/$3

# GitHub CLI api
# https://cli.github.com/manual/gh_api
#gh api --method POST -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" /repos/$2/$3/releases -f "tag_name=$4" -f "target_commitish=master" -f "name=$5" -f "body=Version $4 for MC 1.19.4" -F "draft=false" -F "prerelease=false" -F "generate_release_notes=false"
#gh release upload $4 $1.zip $1-footprints.zip -R $2/$3 --clobber                                            