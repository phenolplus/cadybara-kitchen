import cadquery as cq
import planter_body
import inner_basket
import bracket

# @group Dimensions
width = 150.0       # @param min=100 max=250 unit=mm
depth = 120.0       # @param min=80 max=200 unit=mm
height = 180.0      # @param min=120 max=300 unit=mm
wall_thickness = 3.0 # @param min=1.5 max=5.0 unit=mm
clearance = 0.5     # @param min=0.1 max=1.0 unit=mm

# @group Assembly
show_exploded = False # @param

def build_assembly():
    # Build parts
    p_body = planter_body.build(width, depth, height, wall_thickness, clearance)
    i_basket = inner_basket.build(width, depth, height, 2.0, clearance)
    b_mount = bracket.build(width, depth, height, wall_thickness)
    
    assy = cq.Assembly()
    
    # Main body
    assy.add(p_body, name="planter_body")
    
    # Inner basket sits inside top of main body
    # Positioned so it sits flush with the top
    basket_z = height - (height * 0.7)
    explode_offset_basket = 50 if show_exploded else 0
    assy.add(
        i_basket, 
        name="inner_basket", 
        loc=cq.Location(cq.Vector(0, 0, basket_z + explode_offset_basket))
    )
    
    # Bracket at the back
    # The pocket in planter_body is centered at (0, height/2 + 10, 0) relative to translated planter
    # wait, let's be careful with coordinates.
    # In planter_body.py: planter = planter.translate(cq.Vector(0, -depth/2, 0)) 
    # then pocket was at XZ plane offset 0, translated (0, height/2 + 10, 0)
    # This means the pocket is effectively at the origin of the solid.
    
    explode_offset_bracket = -40 if show_exploded else 0
    assy.add(
        b_mount, 
        name="mounting_bracket",
        loc=cq.Location(cq.Vector(0, explode_offset_bracket, height/2 + 10))
    )
    
    return assy

result = build_assembly()
