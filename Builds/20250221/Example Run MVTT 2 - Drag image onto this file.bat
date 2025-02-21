: This is an example script to execute MVTT with a preselected monitor. The image can just be dragged onto the batch file
: Nr    Parameter         Description
: -     Path to Script    Can be in the same folder as the batch script. Just update the relative path
: 0     Path to Image     Can be given relative to the .exe file
: 1     Monitor Number    Selects the monitor indox for the second window. Valid values: 0...[Monitors connected minus 1]
set arg1=%1
start MVTT.exe %arg1% 1