{
  config,
  pkgs,
  ...
}:
let
  inherit (pkgs) lib;
  mcpNixosNoUpdateCheck = pkgs.writeShellApplication {
    name = "mcp-nixos-no-update-check";
    text = "exec mcp-nixos";
  };
  playwrightMcpWithNixBrowser = pkgs.writeShellApplication {
    name = "playwright-mcp-with-nix-browser";
    text = "exec playwright-mcp";
  };
  # This binding is referenced by name in consumer attrs below.
  slackWriteTools = [
    "slack_send_message"
    "slack_update_canvas"
  ];
in
rec {
  servers = {
    context7 = {
      transport = "http";
      url = "https://mcp.context7.com/mcp";
      auth = {
        kind = "bearer";
        envVar = "CONTEXT7_API_KEY";
      };
      startupTimeoutSec = 10;
      consumers = {
        zed = { mode = "extension"; id = "mcp-server-context7"; };
      };
    };

    exa = {
      transport = "http";
      url = "https://mcp.exa.ai/mcp";
    };

    nixos = {
      transport = "stdio";
      command = lib.getExe mcpNixosNoUpdateCheck;
      args = [ ];
      consumers = {
        opencode.enabled = false;
      };
    };

    playwright = {
      transport = "stdio";
      command = lib.getExe playwrightMcpWithNixBrowser;
      args = [ "--headless" ];
      consumers = {
        opencode.enabled = false;
      };
    };

    slack = {
      transport = "http";
      # mkDefault wrapper and redirectUri must be parsed.
      url = lib.mkDefault "https://mcp.slack.com/mcp";
      oauth = {
        clientId = "12345";
        callbackPort = 3000;
        redirectUri = "http://localhost:3000/callback";
      };
      consumers = {
        pi = { enabled = false; omit = true; };
        opencode.disabledTools = slackWriteTools;
        codex.disabledTools = slackWriteTools;
        pi.excludeTools = slackWriteTools;
      };
    };

    linear = {
      transport = "http";
      url = "https://mcp.linear.app/mcp";
      consumers = {
        codex.defaultToolsApprovalMode = "prompt";
        pi = { enabled = false; omit = true; };
      };
    };

    # Quoted key + ''...'' indented string + comment with a closing brace.
    "mcpGoogleCse" = {
      transport = "stdio";
      command = "${pkgs.uv}/bin/uvx";
      args = [ "mcp-google-cse" ];
      env = {
        # A } inside this comment must not break the parse.
        API_KEY = ''GOOGLE_CSE_API_KEY'';
      };
      consumers = {
        zed.mode = "skip";
      };
    };
  };
}
