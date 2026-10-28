import sys
import os
import ee

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ee.Initialize(project='ee-glassiddo')
from regions_ifl import regions  

base_name = 'ifl_map' # the beginning of the name of each file (e.g., ifl_map_africa_20)
asset_folder = 'projects/ee-glassiddo/assets/' 

# each period combination needs to be run separately. change manually. possible combinations - 00-13; 13-16; 16-20; 20-24 (no loss in 25) 
period_start_year = 20 
period_end_year   = 24

# Official IFL base images per period start year
OFFICIAL_IFL_IMAGES = {
    0:  'users/glassiddo/ifl2000World',
    13: 'users/glassiddo/ifl2013World',
    16: 'users/glassiddo/ifl2016World',
    20: 'users/glassiddo/ifl2020World',
    25: 'users/glassiddo/ifl2025World_b' # accidentally named it this way (with _b) when I uploaded...
}

# the possible deltas - we always care only about the areas that have actually lost status between t_1 to t_2
PERIOD_DELTAS = {
    (0,  13): ('users/glassiddo/ifl2000World', 'users/glassiddo/ifl2013World'),
    (13, 16): ('users/glassiddo/ifl2013World', 'users/glassiddo/ifl2016World'),
    (16, 20): ('users/glassiddo/ifl2016World', 'users/glassiddo/ifl2020World'),
    (20, 24): ('users/glassiddo/ifl2020World', 'users/glassiddo/ifl2025World_b')
}

def get_official_delta(map_focus):
    """
    here we get a binary image of the loss between each period. that's the only period where loss is allowed
    """
    delta_key = (period_start_year, period_end_year)
    if delta_key not in PERIOD_DELTAS: # shouldn't be an issue 
        return None
    ifl_delta_start = ee.Image(PERIOD_DELTAS[delta_key][0]).eq(1).clip(map_focus)
    ifl_delta_end   = ee.Image(PERIOD_DELTAS[delta_key][1]).eq(1).clip(map_focus)
    return ifl_delta_start.And(ifl_delta_end.Not())

forest_threshold = 30 # at least 30% forest cover
export_scale = 30 # the most computationally expensive part - export at 30m. but necessary to maintain shape
mid_coarse_scale = 100 # the loss is grouped and buffered anyway, so can afford to use coarser scale
my_tile_scale = 4 # between 1-16, change depending on performance
max_connected_size = 1024 # maximal value
exclude_fire = True # exclude fire pixels
gte_threshold_patches = 3 # at least 3 connected pixels. tested also 4/5. given we're only allowing loss in known location, use a low threshold
min_original_loss_pixels = 30 # only care about vectors with at least x number of forest loss pixels in them ('road like features' rather than noise)
threshold_area = 500 # km2, based on the rules
buffer_1km = 1000 # m - buffer around loss pixels and erosion
buffer_1km_extra = 1500  # m — dilation after erosion
area_max_error = 1 # could be slightly more as well  but not too high
coarse_area_scale = 200 # for area calculation, coarser resolution
buffer_radius_sml = 100 # to retrieve the full shapes of the loss areas that are below the area threshold 

raw_region_names = [ # only select the ones to run
    'southamerica_southedge', 
    'southamerica_north3', 'southamerica_north2',
    'southamerica_north1', 'southamerica_north4', 'central_america',
    'southamerica_south', 'southamerica_northwest',
    'southamerica_east', 'southamerica_central', 'southamerica_northeast1', 
    'southamerica_northeast2', 'southamerica_centralwest', 
    'africa_eastofcongo', 'africa_westofcongo',
    'westindonesia_malaysia', 'eastindonesia_png',
    'canada_fareast', 'canada_mideast',
    'canada_farwest', 'canada_midwest', 'canada_centre',
    'russia_midfareast', 'russia_centraleast',
    'russia_centralwestsouth', 'russia_centralwestnorth', 'russia_farwest',
    'russia_midwest', 'russia_mideastnorth',
    'russia_mideastsouth', 'russia_veryfareast'
]

regions_to_process = {k: v for k, v in regions.items() if k in raw_region_names}

def build_steps(start_year, end_year): 
    steps = [{'label': f"{start_year}_temp", 'loss_year': None, 'is_temp': True}]
    for y in range(start_year + 1, end_year + 1):
        steps.append({'label': str(y), 'loss_year': y, 'is_temp': False})
    return steps

ALL_STEPS = build_steps(period_start_year, period_end_year)

# ---------------------------------------------------------------------------
# Names and descriptions of assets
# ---------------------------------------------------------------------------

def s1_asset_id(region_name, label):
    """Stage-1 intermediate: post_appendage_ifl"""
    return asset_folder + f"{base_name}_{region_name}_{label}_s1"

def s2_asset_id(region_name, label):
    """Stage-2 final: the IFL map consumed by subsequent steps"""
    return asset_folder + f"{base_name}_{region_name}_{label}"

def s1_desc(region_name, label):
    return f"{base_name}_{region_name}_{label}_s1"

def s2_desc(region_name, label):
    return f"{base_name}_{region_name}_{label}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# always check if an asset exists. if yes, then skip to next one; if not, then run this one
# make sure not to run when there's a relevant running task
def asset_exists(asset_id):
    try:
        ee.data.getAsset(asset_id)
        return True
    except:
        return False

def get_running_tasks():
    tasks = ee.batch.Task.list()
    return {task.config['description']: task for task in tasks
            if task.state in ['READY', 'RUNNING', 'UNSUBMITTED']}

get_running_tasks.cached_tasks = {}
get_running_tasks.last_refresh = 0

def refresh_task_cache():
    get_running_tasks.cached_tasks = get_running_tasks()
    print(f"  Task cache refreshed: {len(get_running_tasks.cached_tasks)} active tasks")

def task_state(desc):
    """Return EE task state string from cache, or None if not found."""
    task = get_running_tasks.cached_tasks.get(desc)
    if task is None:
        return None
    try:
        return task.status()['state']
    except Exception as e:
        print(f"  ✗ Error querying task {desc}: {e}")
        return 'FAILED'


# ---------------------------------------------------------------------------
# part 1 — forest-loss removal + morphological opening → _s1 asset
# ---------------------------------------------------------------------------

def start_stage1(region_name, map_focus, step):
    label = step['label']
    desc  = s1_desc(region_name, label)
    aid   = s1_asset_id(region_name, label)

    if asset_exists(aid):
        return None

    if desc in get_running_tasks.cached_tasks:
        return get_running_tasks.cached_tasks[desc]

    # ── build remaining_ifl ─────────────────────────────────────────────

    if step['is_temp']:
        # if that's the first map running — load the official IFL base map for this period
        official_image_id = OFFICIAL_IFL_IMAGES[period_start_year]
        remaining_ifl = ee.Image(official_image_id).eq(1).clip(map_focus).selfMask()

    else:
        # otherwise, take last year map
        loss_year = step['loss_year']
        if loss_year == period_start_year + 1:
            prev_label = f"{period_start_year}_temp"
        else:
            prev_label = str(loss_year - 1)

        # Use the previous map (part 2, after area calculation) as the base
        ifl_previous_year = ee.Image(s2_asset_id(region_name, prev_label)).selfMask().clip(map_focus)

        # ── Hansen forest loss ───────────────────────────────────────────
        hansen       = ee.Image('UMD/hansen/global_forest_change_2024_v1_12') # most recent version
        forest_cover = hansen.select('treecover2000')
        loss_image   = hansen.select('lossyear')

        # only above forest threshold
        forest_mask    = forest_cover.gte(forest_threshold)
        # only the forest loss year
        loss_year_mask = loss_image.eq(loss_year)

        # ── Fire exclusion ───────────────────────────────────────────────
        if exclude_fire:
            fire_ic   = ee.ImageCollection('users/sashatyu/2001-2023_fire_forest_loss_annual') # doesnt exist for 2024
            fire_loss = fire_ic.map(lambda img: img.eq(loss_year).unmask(0)).max()
            relevant_loss_mask = loss_year_mask.And(fire_loss.Not())
            relevant_loss_mask = relevant_loss_mask.updateMask(relevant_loss_mask)
        else:
            relevant_loss_mask = loss_year_mask

        # only keep loss in forest and the IFL map of the prev year 
        core_loss_in_ifl = relevant_loss_mask.And(forest_mask).And(ifl_previous_year)

        # ── Connected patches ────────────────────────────────────────────
        # use eight connected (diagonal), and if above the threshold 
        patch_size = core_loss_in_ifl.connectedPixelCount(
            maxSize=max_connected_size, eightConnected=True
        )
        connected    = patch_size.gte(gte_threshold_patches)
        # then buffer 1km around them as per IFL rules
        loss_dilated = connected.focal_max(radius=buffer_1km, units='meters').selfMask()

        # to only account for 'large' loss, vectorise at a slightly coarser scale than 30m
        vector_patches = loss_dilated.reduceToVectors(
            geometry=map_focus,
            scale=mid_coarse_scale,
            geometryType='polygon',
            eightConnected=True,
            tileScale=my_tile_scale,
            labelProperty='patch_id',
            maxPixels=1e9
        )
        # and count how many forest loss pixels are in each vector (including not the original x connected)
        vector_with_stats = core_loss_in_ifl.reduceRegions(
            collection=vector_patches,
            reducer=ee.Reducer.sum(),
            scale=mid_coarse_scale,
            tileScale=my_tile_scale
        )
        # only keep vectors with above the threshold
        filtered_vector = vector_with_stats.filter(
            ee.Filter.gte('sum', min_original_loss_pixels)
        )
        # rasterise
        loss_mask     = ee.Image(0).paint(filtered_vector, 1)
        # update the ifl previous year map by removing the buffered loss areas
        remaining_ifl = ifl_previous_year.updateMask(loss_mask.Not())

    # ── Appendage removal ────────────────────────
    # the IFL rules set that appendages/corridors that are 2km wide should be removed
    # done through morphological opening - erosion and then dilation
    # the idea being that this helps getting rid of those appendages/corridors
    buffer_pix     = buffer_1km / export_scale
    buffer_ext_pix = buffer_1km_extra / export_scale

    binary  = remaining_ifl.selfMask().unmask(0)
    eroded  = binary.focal_min(radius=buffer_pix)
    dilated = eroded.focal_max(radius=buffer_ext_pix)
    post_appendage_ifl = dilated.updateMask(remaining_ifl).selfMask()

    # ── Export the post-loss and appendage asset ───────────────────────────────────────────────────────────
    task = ee.batch.Export.image.toAsset(
        image=post_appendage_ifl,
        description=desc,
        assetId=aid,
        region=map_focus,
        scale=export_scale,
        maxPixels=1e13,
        pyramidingPolicy={'result': 'mode'}
    )
    task.start()
    print(f"  ✓ [S1] Started: {desc}")
    return task


# ---------------------------------------------------------------------------
# Part 2 — remove small areas
# not sure strictly why it's necessary, but when I tried running all in a single asset there were issues
# as it was using the coarser resolution for everything and creating weird shapes
# it works now and part 2 is not computationally intensive at all
# ---------------------------------------------------------------------------

# get the part 1 IFL for the year, vectorise at coarser scale to compute roughly the area 
# and then remove the small areas (slightly buffer them to get the full original shape to be removed) 
def start_stage2(region_name, map_focus, step):
    label = step['label']
    desc  = s2_desc(region_name, label)
    aid   = s2_asset_id(region_name, label)

    if asset_exists(aid):
        return None

    if desc in get_running_tasks.cached_tasks:
        return get_running_tasks.cached_tasks[desc]

    post_appendage_ifl = ee.Image(s1_asset_id(region_name, label)).selfMask()

    coarse_vectors = post_appendage_ifl.reduceToVectors(
        geometry=map_focus,
        scale=coarse_area_scale,
        geometryType='polygon',
        eightConnected=True,
        tileScale=my_tile_scale,
        maxPixels=1e13
    )

    vectors_with_area = coarse_vectors.map(
        lambda f: f.set('area_km2', f.geometry().area(area_max_error).divide(1e6)) # area calc
    )

    small_patches = vectors_with_area.filter(ee.Filter.lt('area_km2', threshold_area))

    small_mask = ee.Image(0).paint(small_patches, 1).selfMask()
    small_mask_dilated = small_mask.focal_max(
        radius=buffer_radius_sml, units='meters'
    ).unmask(0)

    not_small = small_mask_dilated.Not() # the ones to be kept
    final_raster = post_appendage_ifl.updateMask(not_small).clip(map_focus)

    # make sure it happens in areas that have actually lost IFL status in that period
    official_delta = get_official_delta(map_focus)
    official_base = ee.Image(OFFICIAL_IFL_IMAGES[period_start_year]).eq(1).clip(map_focus)
    must_keep = official_base.updateMask(official_delta.Not())
    final_raster = final_raster.unmask(0).Or(must_keep.unmask(0)).selfMask().clip(map_focus)

    task = ee.batch.Export.image.toAsset(
        image=final_raster,
        description=desc,
        assetId=aid,
        region=map_focus,
        scale=export_scale,
        maxPixels=1e13,
        pyramidingPolicy={'result': 'mode'}
    )
    task.start()
    print(f"  ✓ [S2] Started: {desc}")
    return task


# ---------------------------------------------------------------------------
# State machine - written by LLM...
# Each region tracks: step_index, stage (1 or 2), active task description
# ---------------------------------------------------------------------------

region_states = {}
for region_name in regions_to_process.keys():
    region_states[region_name] = {
        'step_index': 0,    # index into ALL_STEPS
        'stage':      1,    # 1 or 2
        'task_id':    None, # description string of the active EE task
        'completed':  False,
        'failed':     False,
    }


def get_active_regions():
    return {name: state for name, state in region_states.items()
            if not state['completed'] and not state['failed']}


def advance_region(region_name, state, map_focus):
    """
    Drive the state machine for one region for one polling cycle.
    Checks the active task, then starts the next task if ready.
    """
    if state['step_index'] >= len(ALL_STEPS):
        state['completed'] = True
        print(f"  ✓ All steps completed!")
        return

    step  = ALL_STEPS[state['step_index']]
    stage = state['stage']
    label = step['label']

    # Which asset are we currently waiting for?
    current_aid = s1_asset_id(region_name, label) if stage == 1 else s2_asset_id(region_name, label)

    # ── Check active task status ─────────────────────────────────────────
    if state['task_id'] is not None:
        ts = task_state(state['task_id'])

        if ts in ('READY', 'RUNNING', 'UNSUBMITTED'):
            print(f"  ⟳ [S{stage}] '{label}' still {ts}...")
            return

        elif ts == 'COMPLETED':
            print(f"  ✓ [S{stage}] '{label}' task completed.")
            state['task_id'] = None
            # fall through to start next stage/step

        elif ts in ('FAILED', 'CANCELLED'):
            print(f"  ✗ [S{stage}] '{label}' FAILED. Skipping region.")
            state['failed'] = True
            return

        else:
            # ts is None — task not in active cache; verify by checking asset
            if asset_exists(current_aid):
                print(f"  ✓ [S{stage}] '{label}' asset exists (task cache miss).")
                state['task_id'] = None
                # fall through
            else:
                # Task vanished and asset not yet visible — wait one more cycle
                print(f"  ? [S{stage}] '{label}' task not in cache, asset missing — waiting.")
                return

    # ── No active task: start next stage or advance to next step ─────────
    if stage == 1:
        if asset_exists(s1_asset_id(region_name, label)):
            print(f"  [S1] '{label}' already exists, advancing to S2.")
            state['stage'] = 2
            advance_region(region_name, state, map_focus)  # recurse into S2
        else:
            task = start_stage1(region_name, map_focus, step)
            if task is None:
                # asset already exists (start_stage1 double-checks)
                state['stage'] = 2
                advance_region(region_name, state, map_focus)
            else:
                state['task_id'] = s1_desc(region_name, label)

    elif stage == 2:
        if asset_exists(s2_asset_id(region_name, label)):
            print(f"  [S2] '{label}' already exists, advancing to next step.")
            _next_step(region_name, state, map_focus)
        else:
            task = start_stage2(region_name, map_focus, step)
            if task is None:
                _next_step(region_name, state, map_focus)
            else:
                state['task_id'] = s2_desc(region_name, label)


def _next_step(region_name, state, map_focus):
    """Advance to the next step and immediately kick off its Stage 1."""
    state['step_index'] += 1
    state['stage']      = 1
    state['task_id']    = None

    if state['step_index'] >= len(ALL_STEPS):
        print(f"  ✓ All steps processed. Region {region_name} completed!")
        state['completed'] = True
    else:
        next_label = ALL_STEPS[state['step_index']]['label']
        print(f"  → Next step: '{next_label}', starting S1...")
        advance_region(region_name, state, map_focus)


# ---------------------------------------------------------------------------
# Main polling entry point
# ---------------------------------------------------------------------------

def check_status_and_run():
    refresh_task_cache()

    active_regions = get_active_regions()
    if not active_regions:
        print("All regions completed or failed.")
        return

    for region_name, state in active_regions.items():
        step  = ALL_STEPS[state['step_index']] if state['step_index'] < len(ALL_STEPS) else None
        label = step['label'] if step else 'done'
        print(f"\nRegion: {region_name} | Step {state['step_index']+1}/{len(ALL_STEPS)}: "
              f"'{label}' S{state['stage']} | Task: {state['task_id']}")
        advance_region(region_name, state, regions[region_name])

    active_regions = get_active_regions()
    active_tasks   = sum(1 for s in active_regions.values() if s['task_id'] is not None)
    completed      = sum(1 for s in region_states.values() if s['completed'])
    failed         = sum(1 for s in region_states.values() if s['failed'])

    print(f"\n{'='*60}")
    print(f"Period: {period_start_year} → {period_end_year}  |  "
          f"Steps: {[s['label'] for s in ALL_STEPS]}")
    print(f"Status: {active_tasks} active tasks | {len(active_regions)} regions running")
    print(f"        {completed} completed | {failed} failed")


check_status_and_run()
