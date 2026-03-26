Set shell = CreateObject("WScript.Shell")
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
command = "cmd /c """ & scriptDir & "\launch_control_room_hidden.cmd"""
shell.Run command, 0, False
