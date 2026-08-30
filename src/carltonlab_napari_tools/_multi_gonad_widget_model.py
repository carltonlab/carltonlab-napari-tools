import os
from configparser import ConfigParser


def file_available(file_path: str) -> bool:
    return not os.path.exists(file_path)


def make_directories_dict(
    current_dictionary: dict[str, str], directories: list[str]
) -> dict[str, str]:
    for clsp_dir in directories:
        base_name = os.path.basename(clsp_dir)
        current_dictionary[base_name] = clsp_dir
    return current_dictionary


def create_project_file(dir_dict: dict[str, str], project_path: str) -> bool:
    if not file_available(project_path):
        return False
    config_parser: ConfigParser = ConfigParser()
    config_parser.add_section("GonadDirectoryNames")
    config_parser.add_section("GonadDirectoryPaths")
    config_parser.add_section("GonadCompleted")
    for gonad_index in range(len(dir_dict)):
        keys_list = list(dir_dict.keys())
        gonad_dir_name = keys_list[gonad_index]
        gonad_file_path = dir_dict[gonad_dir_name]
        gonad_string = "gonad-" + str(gonad_index + 1)
        config_parser["GonadDirectoryNames"][gonad_string] = gonad_dir_name
        config_parser["GonadDirectoryPaths"][gonad_string] = gonad_file_path
        config_parser["GonadCompleted"][gonad_string] = "False"
    with open(project_path, "w") as config_file:
        config_parser.write(config_file)
    return True
