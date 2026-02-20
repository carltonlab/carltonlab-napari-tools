def parse_string_for_channels(parsing_string: str) -> list[int]:
    if parsing_string == "":
        return []
    channels: list[int] = []
    parts = [part for part in parsing_string.split(",") if part != ""]
    for part in parts:
        if "-" in part:
            start_text, end_text = part.split("-", maxsplit=1)
            if start_text == "" or end_text == "":
                return []
            start_value = int(start_text)
            end_value = int(end_text)
            if start_value > end_value:
                start_value, end_value = end_value, start_value
            channels.extend(range(start_value, end_value + 1))
        else:
            channels.append(int(part))
    return channels


def extract_channels(
    file_list: list[str],
    dir_list: list[str],
    extracting_channels_string: str,
    save_directory: str | None = None,
) -> bool:
    channels = parse_string_for_channels(extracting_channels_string)
    print(f"Extracting channels: {channels}")
    if save_directory is not None:
        print(f"Saving to directory: {save_directory}")
    return True
