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
      url = "https://mcp.slack.com/mcp";
      oauth = {
        clientId = "12345";
        callbackPort = 3000;
      };
      consumers = {
        pi = { enabled = false; omit = true; };
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

    mcpGoogleCse = {
      transport = "stdio";
      command = "${pkgs.uv}/bin/uvx";
      args = [ "mcp-google-cse" ];
      env = {
        API_KEY = "GOOGLE_CSE_API_KEY";
      };
      consumers = {
        zed.mode = "skip";
      };
    };
  };
}
