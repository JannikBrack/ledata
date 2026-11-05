// Shared dimensions for all WS2812B rail parts.
// Keep model-specific dimensions in their respective .scad files.

led_width = 10;
led_height = 5;
led_side_clearance = 1;
base_thickness = 2;
wall_thickness = 2.6;
wall_height = 9.5;
print_clearance = 0.25;

hook_length = 5.5;
hook_beam_width = 1.2;
hook_beam_height = 1.0;
hook_position_z = 4.9;
hook_nose_length = 1.1;
socket_length = 6.2;

channel_width = led_width + 2 * led_side_clearance;
rail_width = channel_width + 2 * wall_thickness;
rail_height = base_thickness + wall_height;
socket_throat_length = hook_length - hook_nose_length - 3 * print_clearance;
epsilon = 0.02;
