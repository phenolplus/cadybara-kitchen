import cadquery as cq
import math

# @group Overall Dimensions
width = 120.0       # @param min=80 max=200 unit=mm
depth = 100.0       # @param min=60 max=150 unit=mm
height = 110.0      # @param min=50 max=200 unit=mm
wall_thickness = 5.0 # @param min=3 max=10 unit=mm

# @group Internal Cavity
pot_top_diam = 90.0    # @param min=50 max=150 unit=mm
pot_bottom_diam = 85.0 # @param min=40 max=140 unit=mm
pot_depth = 95.0       # @param min=40 max=180 unit=mm
drain_hole_diam = 6.0  # @param min=0 max=15 unit=mm

# @group Mounting
keyhole_entry_diam = 10.0 # @param min=8 max=15 unit=mm
keyhole_slot_width = 5.0  # @param min=3 max=8 unit=mm
keyhole_depth = 8.0       # @param min=5 max=15 unit=mm

def build_planter():
    # 1. Create the main tapered hexagonal body
    # We want a flat back, so we will use a hexagonal base but sliced or positioned
    # such that the rear is flat on the YZ plane (or parallel).
    
    # Calculate hexagonal radius (from center to vertex) based on width
    # In a regular hexagon, width (side-to-side) is 2 * r * cos(30).
    # Since we want a flat back, we'll use a polygon and then slice it.
    hex_radius = width / math.sqrt(3)
    
    # We use a taper. 'taper' in extrude is degrees. 
    # Let's target a slight narrowing at the bottom.
    taper_angle = 5.0 
    
    # Base shape: Hexagon
    # To get a flat back at X=0, we center the hexagon and move it or rotate it.
    # Default polygon is centered at origin.
    body = (
        cq.Workplane("XY")
        .polygon(6, hex_radius * 2)
        .extrude(height, taper=taper_angle)
    )
    
    # 2. Flatten the back face
    # We want the back to be flat for mounting.
    # The hexagon is centered. Let's cut it at a specific Y to make a flat face.
    # Width is 120. Half-width 60. 
    back_cut_y = (width / 2) * 0.4 # Adjust to get a nice flat surface
    
    # Move body so the flat back is at Y=0
    # Actually, let's just use a box-intercept or a cut to ensure a flat back.
    body = body.translate((0, depth/2 - (width/math.sqrt(3))/2, 0)) # Approximate centering
    
    # Let's refine the body: start from the back plane
    # Base of the hexagon will be at the front, flat face at the back.
    
    planter = (
        cq.Workplane("XZ") # Vertical plane for the back
        .rect(width, height)
        .extrude(-depth) # Extrude forward
    )
    
    # Now intersect this box with a tapered hexagonal prism to get the stylized look
    hex_prism = (
        cq.Workplane("XY")
        .workplane(offset=0) # Bottom
        .polygon(6, (width * 1.1) / math.sqrt(3))
        .workplane(offset=height) # Top
        .polygon(6, width / math.sqrt(3))
        .loft(combine=False)
    )
    
    # Move hex_prism so its "back" side coincides with plane Y=0
    # The distance from center to a flat side of a hexagon is r * cos(30)
    # distance = (width/math.sqrt(3)) * (math.sqrt(3)/2) = width/2
    hex_prism = hex_prism.translate((0, width/2, 0))
    
    # The resulting body is the intersection (stylized front, flat back)
    # But simpler: start with the hex prism, then cut the back flat.
    final_body = (
        cq.Workplane("XY")
        .polygon(6, (width * 1.2) / math.sqrt(3))
        .extrude(height, taper=-taper_angle) # Taper outwards as we go up
        .translate((0, 0, 0))
    )
    
    # Cut the back to be flat at Y = -10 (some offset from center)
    back_plane_y = -width/4
    final_body = final_body.cut(
        cq.Workplane("XY")
        .workplane(offset=-1.0) # slightly below bottom
        .rect(width*2, width*2)
        .extrude(height+2.0)
        .translate((0, back_plane_y - width, 0))
    )
    
    # 3. Create Internal Cavity
    # Cylindrical centered cavity
    cavity = (
        cq.Workplane("XY")
        .workplane(offset=height - pot_depth)
        .circle(pot_bottom_diam / 2)
        .workplane(offset=pot_depth)
        .circle(pot_top_diam / 2)
        .loft(combine=False)
    )
    
    # Position cavity: centered in X, but shifted forward in Y to maintain wall thickness at back
    cavity_y_offset = (pot_top_diam / 2) - (width/2) + back_plane_y + wall_thickness + 10 # heuristic
    # Let's just center it relative to the flat back
    cavity_y = back_plane_y + wall_thickness + (pot_top_diam / 2)
    cavity = cavity.translate((0, cavity_y, 0))
    
    # Subtract cavity
    planter_solid = final_body.cut(cavity)
    
    # 4. Mounting Interface (Keyhole)
    # The back face is at Y = back_plane_y
    # Entry hole (bottom part of keyhole)
    # Slot (upper part)
    
    keyhole_z_center = height * 0.75 # Place in upper part
    keyhole_y = back_plane_y
    
    # Entry hole (large)
    planter_solid = (
        planter_solid.faces("<Y") # Select the flat back
        .workplane(centerOption="CenterOfMass")
        .moveTo(0, keyhole_z_center - (height/2) - 10) # Position relative to face center
        .cboreHole(keyhole_slot_width, keyhole_entry_diam, keyhole_depth - 4, depth=keyhole_depth)
    )
    
    # The cboreHole makes a round seat. We need a vertical slot above it.
    # Manually cut the slot for the screw shank
    slot_length = 15.0
    planter_solid = (
        planter_solid.faces("<Y")
        .workplane(centerOption="CenterOfMass")
        .moveTo(0, keyhole_z_center - (height/2) - 10)
        .move(0, slot_length / 2)
        .rect(keyhole_slot_width, slot_length)
        .cutBlind(-keyhole_depth)
    )
    
    # Also need the "head" clearance behind the slot
    planter_solid = (
        planter_solid.faces("<Y")
        .workplane(centerOption="CenterOfMass")
        .moveTo(0, keyhole_z_center - (height/2) - 10)
        .move(0, slot_length / 2)
        .rect(keyhole_entry_diam, slot_length)
        .cutBlind(-(keyhole_depth - 3)) # leave a shoulder for the screw head
    )
    
    # 5. Drainage Hole
    # From cavity bottom to the outside (bottom of planter)
    drain_start_z = height - pot_depth
    planter_solid = (
        planter_solid.union(
            cq.Workplane("XY")
            .workplane(offset=0)
            .circle(drain_hole_diam / 2)
            .extrude(drain_start_z + 2)
            .translate((0, cavity_y, -1))
        ) # this was a union of a cylinder, but we want to cut it.
    )
    # Correcting: use cut
    drain_hole = (
        cq.Workplane("XY")
        .workplane(offset=-1)
        .circle(drain_hole_diam / 2)
        .extrude(drain_start_z + 5)
        .translate((0, cavity_y, 0))
    )
    planter_solid = planter_solid.cut(drain_hole)
    
    # 6. Stability Lip (1mm perimeter lip on back)
    # We can do this by offsetting the back face's outer wire slightly and extruding
    back_face = planter_solid.faces("<Y").workplane()
    # For simplicity, we can just cut a pocket into the back to leave a lip
    planter_solid = (
        back_face
        .rect(width - 4, height - 4) # leave 2mm rim
        .cutBlind(-1.0)
    )

    return planter_solid

result = build_planter()
