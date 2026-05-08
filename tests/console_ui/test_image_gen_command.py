from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text("utf-8")


def test_image_gen_command_uses_chat_input_instead_of_panel() -> None:
    commands = read("console-ui/src/pages/ChatPage/commands.ts")
    chat_input = read("console-ui/src/pages/ChatPage/ChatInput.tsx")

    assert "id: '/image-gen'" in commands
    assert "populateOnly: true" in commands
    assert "openImageGenPanel" not in commands
    assert "ImageGenPanel" not in chat_input
    assert "image-gen)(?:\\s+" in chat_input


def test_image_gen_command_uploads_attachment_as_reference_path() -> None:
    chat_input = read("console-ui/src/pages/ChatPage/ChatInput.tsx")

    assert "uploadImageGenReference" in chat_input
    assert "'/chat/uploads'" in chat_input
    assert "upload?.path || upload?.media_path" in chat_input
    assert "reference_image: referenceImage" in chat_input
    assert "directTask.taskType !== 'image_gen'" in chat_input
    assert "/image-gen reference 必须是图片文件" in chat_input


def test_image_gen_command_has_local_submit_lock_and_no_chat_fallthrough() -> None:
    chat_input = read("console-ui/src/pages/ChatPage/ChatInput.tsx")

    assert "localSubmittingRef.current" in chat_input
    assert "setLocalSubmitting(true)" in chat_input
    assert "const busy = sendDisabled || localSubmitting" in chat_input
    direct_branch = chat_input.split("if (directTask) {", 1)[1].split("localSubmittingRef.current = true", 2)[1]
    assert "return" in direct_branch.split("localSubmittingRef.current = true", 1)[0]
