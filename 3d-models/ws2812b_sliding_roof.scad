// Flat, lengthwise-sliding cover for ws2812b_modular_rail.scad.
// Match rail_length to the rail segment and export a 4 mm shorter cover.

rail_length = 200;
end_clearance = 2;
print_clearance = 0.25;

led_width = 10;
led_side_clearance = 1;
wall_thickness = 2.6;
roof_slot_depth = 1.5;
roof_slot_height = 1.5;
roof_slot_bottom = 8;
rail_base_thickness = 2;
rail_wall_height = 9.5;

cover_thickness = 1.2;
cover_tab_thickness = 0.8;
cover_side_clearance = 0.25;

channel_width = led_width + 2 * led_side_clearance;
groove_depth = roof_slot_depth + print_clearance;
cover_length = rail_length - 2 * end_clearance;
cover_body_width = channel_width - 2 * cover_side_clearance;
cover_tab_outer_edge = channel_width / 2 + groove_depth - cover_side_clearance;

module roof_cross_section() {
    union() {
        translate([0, -cover_body_width / 2])
            square([cover_thickness, cover_body_width]);

        translate([
            (cover_thickness - cover_tab_thickness) / 2,
            -cover_tab_outer_edge
        ])
            square([
                cover_tab_thickness,
                cover_tab_outer_edge - cover_body_width / 2
            ]);
        translate([
            (cover_thickness - cover_tab_thickness) / 2,
            cover_body_width / 2
        ])
            square([
                cover_tab_thickness,
                cover_tab_outer_edge - cover_body_width / 2
            ]);
    }
}

assert(rail_length > 2 * end_clearance,
    "rail_length must be greater than twice end_clearance");
assert(roof_slot_bottom + roof_slot_height <= rail_base_thickness + rail_wall_height,
    "The roof groove must remain inside the rail wall");
assert(cover_tab_thickness + print_clearance <= roof_slot_height,
    "The roof tabs need clearance inside the rail grooves");
assert(wall_thickness > groove_depth,
    "The rail needs a wall behind the roof groove");

translate([cover_length, 0, 0])
    rotate([0, -90, 0])
        linear_extrude(height = cover_length)
            roof_cross_section();
