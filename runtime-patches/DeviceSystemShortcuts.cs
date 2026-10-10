using IPhoneMirror.App.Services;

namespace IPhoneMirror.App.Services.Automation;

// Called under the lease operation lock and the captured session's keyboard gate.
internal static class DeviceSystemShortcuts
{
    internal static readonly string[] Names = ["home", "app_switcher", "control_center",
        "notification_center", "dock", "siri", "volume_up", "volume_down", "lock_screen"];

    internal static string[] Supported(DirectKeyboardRoute? route) =>
        route is not null && (route.SendShortcutAsync is not null || route.SendButtonAsync is not null)
            ? Names.ToArray() : [];

    internal static async Task SendAsync(DirectKeyboardRoute route, string? shortcut,
        Func<bool> current, CancellationToken cancellation)
    {
        if (!Names.Contains(shortcut))
            throw new AutomationException("INVALID_REQUEST", "Unsupported shortcut name.", 400);
        if (!Supported(route).Contains(shortcut))
            throw new AutomationException("CAPABILITY_NOT_SUPPORTED", "System shortcuts are unavailable on this transport.", 422);
        bool CanSend() => !cancellation.IsCancellationRequested && current() && route.IsCurrent();
        void Check()
        {
            cancellation.ThrowIfCancellationRequested();
            if (!CanSend()) throw new OperationCanceledException();
        }
        Check();
        if (route.SendShortcutAsync is { } bluetooth)
        {
            // The Bluetooth delegate captures its generation and target; its existing
            // report helpers release consumer/navigation/keyboard reports on failure.
            await bluetooth(shortcut!, CanSend).ConfigureAwait(false);
            Check();
            return;
        }
        const ushort page = CoreDeviceTouchProtocol.IndigoConsumerUsagePage;
        async Task ReleaseKeyboard() => await route.SendAsync(0, [], null).ConfigureAwait(false);
        async Task ReleaseGlobe() => await route.SendButtonAsync!(page,
            CoreDeviceTouchProtocol.GlobeKeyboardLayoutUsage, "up", null).ConfigureAwait(false);
        async Task Pulse(ushort usage, int holdMs)
        {
            Check();
            try
            {
                await route.SendButtonAsync!(page, usage, "down", CanSend).ConfigureAwait(false);
                await Task.Delay(holdMs, cancellation).ConfigureAwait(false);
            }
            finally
            {
                // Cleanup remains bound to the original session and ignores lease
                // cancellation. Never send an up to a replacement route.
                if (route.IsCurrent())
                    await route.SendButtonAsync!(page, usage, "up", null)
                        .WaitAsync(TimeSpan.FromSeconds(1)).ConfigureAwait(false);
            }
        }
        switch (shortcut)
        {
            case "home": await Pulse(CoreDeviceTouchProtocol.IndigoHome, 50); break;
            case "app_switcher":
                await Pulse(CoreDeviceTouchProtocol.IndigoHome, 50);
                await Task.Delay(100, cancellation).ConfigureAwait(false);
                await Pulse(CoreDeviceTouchProtocol.IndigoHome, 50);
                break;
            case "siri": await Pulse(CoreDeviceTouchProtocol.IndigoSiri, 1000); break;
            case "volume_up": await Pulse(CoreDeviceTouchProtocol.IndigoVolumeUp, 50); break;
            case "volume_down": await Pulse(CoreDeviceTouchProtocol.IndigoVolumeDown, 50); break;
            case "lock_screen": await Pulse(CoreDeviceTouchProtocol.IndigoLock, 500); break;
            default:
                var usage = shortcut switch { "control_center" => (byte)0x06,
                    "notification_center" => (byte)0x11, "dock" => (byte)0x04, _ => (byte)0 };
                try
                {
                    await route.SendButtonAsync!(page, CoreDeviceTouchProtocol.GlobeKeyboardLayoutUsage,
                        "down", CanSend).ConfigureAwait(false);
                    Check();
                    await route.SendAsync(0, [usage], CanSend).ConfigureAwait(false);
                    await Task.Delay(20, cancellation).ConfigureAwait(false);
                }
                finally
                {
                    if (route.IsCurrent())
                        await Task.WhenAll(
                            ReleaseKeyboard(), ReleaseGlobe())
                            .WaitAsync(TimeSpan.FromSeconds(1)).ConfigureAwait(false);
                }
                break;
        }
        Check();
    }
}
