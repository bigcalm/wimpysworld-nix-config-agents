{
  config,
  lib,
  ...
}:
{
  programs.opencode = {
    enable = true;
    settings = {
      autoupdate = false;
      model = "openai/gpt-5.5";
      tui = {
        tui = {
          diff_style = "stacked";
          scroll_acceleration = { enabled = true; };
        };
      };
      keybinds = {
        app_exit = "ctrl+d";
        input_submit = "return";
      };
      command = {
        init = {
          description = "Create AGENTS.md";
          agent = "rosey";
          template = builtins.readFile ../assistants/agents/rosey/commands/create-agents-md/prompt.md;
        };
      };
    };
  };
}
