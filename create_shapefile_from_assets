// List of years to process
var years = ee.List.sequence(2001, 2020);

var regions = [
  'africa_eastofcongo', 'africa_westofcongo', 
  'canada_centre', 'canada_fareast', 'canada_farwest', 
  'canada_mideast', 'canada_midwest',
  'eastindonesia_png', 'westindonesia_malaysia',
  'russia_midfareast', 'russia_mideastnorth', 
  'russia_farwest', 'russia_centraleast',
  'russia_veryfareast', 'russia_midwest', 'russia_mideastsouth',
  'russia_centralwestsouth', 'russia_centralwestnorth',
  'southamerica_east', 'southamerica_northwest',
  'southamerica_central', 'southamerica_centralwest', 
  'southamerica_northeast1', 'southamerica_northeast2',
  'southamerica_south', 'central_america', 'southamerica_north1', 
  'southamerica_north3', 'southamerica_north4'
];

// Function to load the image based on year and region
function getImage(year, region, version) {
  var assetName = 'projects/ee-glassiddo/assets/' + year + region;
  if (version) {
    assetName += '_' + version;
  }
  return ee.Image(assetName);
}

// Function to get the geometry of all regions combined
function getCombinedGeometry() {
  var geometries = regions.map(function(region) {
    return getImage(2001, region).geometry();
  });
  
  var combined = ee.Geometry(geometries[0]);
  for (var i = 1; i < geometries.length; i++) {
    combined = combined.union(geometries[i]);
  }
  
  return combined;
}

var combinedGeometry = getCombinedGeometry();

// Function to compute the difference between two years for all regions
function getDifference(currentYear) {
  var previousYear = currentYear - 1;
  
  var differences = regions.map(function(region) {
    var currentImage, previousImage;
    
    if (currentYear === 2016) {
      currentImage = getImage(currentYear, region, 'v2'); // 2016 for 2013-2016 run
      previousImage = getImage(2015, region); 
      var ownImage = getImage(2016, region, 'own'); // 2016_own (official map without loss)
      var regularImage = getImage(2016, region) // 2016 (official map + loss, 2016-2020)
      
      var currentMask = currentImage.mask();
      var prevMask = previousImage.mask();
      var ownMask = ownImage.mask();
      var regularMask = regularImage.mask();
      
      return prevMask.and(currentMask.not())
        .or(ownMask.and(regularMask.not()))
        .selfMask();
    } else if (currentYear === 2013) {
      currentImage = getImage(currentYear, region, 'v2'); // 2013 for 2000-2013 run
      previousImage = getImage(2012, region);
      var ownImage = getImage(2013, region, 'own'); // 2013_own (official map without loss)
      var regularImage = getImage(2013, region) // 2013 (official map + loss, 2013-2016)

      var currentMask = currentImage.mask();
      var prevMask = previousImage.mask();
      var ownMask = ownImage.mask();
      var regularMask = regularImage.mask();

      return prevMask.and(currentMask.not())
        .or(ownMask.and(regularMask.not()))
        .selfMask();
    } else {
      currentImage = getImage(currentYear, region);
      previousImage = getImage(previousYear, region);
      
      var currentMask = currentImage.mask();
      var prevMask = previousImage.mask();
      
      return prevMask.and(currentMask.not()).selfMask();
    }
  });
  
  return ee.ImageCollection(differences).mosaic().set('year', currentYear);
}

// Function to process a single year
function processYear(year) {
  var differenceImage = getDifference(year);
  
  // Map.addLayer(differenceImage, {palette: ['red']}, 'IFL Loss ' + year);
  
  var vectorized = differenceImage.reduceToVectors({
    geometry: combinedGeometry,
    scale: 30,
    eightConnected: false,
    maxPixels: 1e13
  });
  
  var diffMap = vectorized.map(function(feature) {
    return feature.set('year', year - 2000);
  });
  
  Export.table.toDrive({
    collection: diffMap,
    description: 'IFL' + year,
    fileFormat: 'SHP',
    fileNamePrefix: 'IFL_Loss_' + year
  });
}

// Process each year
years.evaluate(function(yearList) {
  yearList.forEach(function(year) {
    processYear(year);
  });
});
