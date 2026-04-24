// change 'year' and 'extra' accordingly
var year = '_20';
var extra = '_temp' // _own, _v2, or empty

var regions = [
   'southamerica_southedge', 'southamerica_north3', 'southamerica_north2',
   'southamerica_north1', 'southamerica_north4', 'central_america',
    'southamerica_south', 'southamerica_northwest',
    'southamerica_east', 'southamerica_central', 'southamerica_northeast1', 
    'southamerica_northeast2', 'southamerica_centralwest', 
    'africa_eastofcongo', 'africa_westofcongo',
    'westindonesia_malaysia', 'eastindonesia_png',
    'canada_fareast', 'canada_mideast', 'canada_farwest', 'canada_midwest', 'canada_centre', 
    'russia_midfareast', 'russia_centraleast',
    'russia_centralwestsouth', 'russia_farwest', 'russia_centralwestnorth', 
    'russia_midwest', 'russia_mideastnorth',
    'russia_mideastsouth', 'russia_veryfareast'
  ];  

function loadRegionImage(region, year) {
  var assetPath = 'projects/ee-glassiddo/assets/' + 'ifl_map_' + region + year + extra;
  return ee.Image(assetPath).toInt().eq(1);
}

// Function to combine images for multiple regions
function combineRegions(regions, year) {
  var images = regions.map(function(region) {
    return loadRegionImage(region, year);
  });
  return ee.ImageCollection(images).mosaic();
}

// Set the map type to terrain
Map.setOptions('TERRAIN');

// Combine the images
var combined = combineRegions(regions, year);

// Visualize the result
Map.addLayer(combined, {palette: ['black']}, 'Combined ' + year);

Export.image.toAsset({
  image: combined,               // The image to export
  description: 'combined2020_temp',   // A description for the export task
  assetId: 'combined2020_temp', 
  region: combined.geometry().bounds(),
  scale: 30,                     // Spatial resolution in meters (adjust as needed)
  maxPixels: 1e13                // Max number of pixels allowed in the export
});
