using IPhoneMirror.App.Services;
using IPhoneMirror.App.Services.Automation;

static void Check(bool condition, string message)
{
    if (!condition) throw new Exception(message);
}

var packets = new List<string>();
bool live = true;
Func<ushort, ushort, string, Func<bool>?, Task> button = (page, code, phase, guard) =>
{
    Check(guard?.Invoke() != false, "Invalid press guard");
    packets.Add($"{page:x}:{code:x}:{phase}");
    return Task.CompletedTask;
};
var route = new DirectKeyboardRoute(() => live, (modifier, usages, guard) =>
{
    packets.Add("key:" + string.Join(",", usages));
    return Task.CompletedTask;
}, button);
Check(DeviceSystemShortcuts.Supported(null).Length == 0, "Null route advertised shortcuts");
Check(DeviceSystemShortcuts.Supported(route).Length == 9, "Missing supported actions");
foreach (var name in DeviceSystemShortcuts.Names)
{
    packets.Clear();
    await DeviceSystemShortcuts.SendAsync(route, name, () => true, default);
    Check(packets.Count > 0, "Shortcut silently did nothing");
    if (name == "app_switcher")
        Check(packets.SequenceEqual(new[] { "c:40:down", "c:40:up", "c:40:down", "c:40:up" }), "App switcher is not a double Home pulse");
    if (name is "control_center" or "notification_center" or "dock")
        Check(packets[0] == "c:29d:down" && packets.Contains("key:") && packets[^1] == "c:29d:up", "Globe chord was not released");
}
// Cancellation after press must release exactly once, even though guard is revoked.
using (var cancel = new CancellationTokenSource())
{
    packets.Clear();
    var cancelled = route with { SendButtonAsync = (page, code, phase, guard) =>
    {
        packets.Add(phase);
        if (phase == "down") cancel.Cancel();
        else Check(guard is null, "Cleanup was gated by cancelled lease");
        return Task.CompletedTask;
    } };
    try { await DeviceSystemShortcuts.SendAsync(cancelled, "siri", () => true, cancel.Token); throw new Exception("Cancellation ignored"); }
    catch (OperationCanceledException) { }
    Check(packets.SequenceEqual(new[] { "down", "up" }), "Cancellation did not release pressed button");
}
// A failed down may already have reached the device. Release; do not retry it.
packets.Clear();
var failed = route with { SendButtonAsync = (page, code, phase, guard) =>
{
    packets.Add(phase);
    return phase == "down" ? Task.FromException(new IOException("uncertain")) : Task.CompletedTask;
} };
try { await DeviceSystemShortcuts.SendAsync(failed, "home", () => true, default); throw new Exception("Failure ignored"); }
catch (IOException) { }
Check(packets.SequenceEqual(new[] { "down", "up" }), "Failed button retried or not released");
// A failing Globe press must release both report types.
packets.Clear();
try { await DeviceSystemShortcuts.SendAsync(failed, "control_center", () => true, default); throw new Exception("Failure ignored"); }
catch (IOException) { }
Check(packets.Contains("key:") && packets.Count(p => p == "down") == 1 && packets.Count(p => p == "up") == 1, "Globe failure leaked reports");
packets.Clear();
var syncFailure = route with { SendAsync = (modifier, usages, guard) => throw new IOException("synchronous failure") };
try { await DeviceSystemShortcuts.SendAsync(syncFailure, "dock", () => true, default); throw new Exception("Failure ignored"); }
catch (IOException) { }
Check(packets.SequenceEqual(new[] { "c:29d:down", "c:29d:up" }), "Keyboard failure prevented Globe cleanup");
// Never clean up on a replacement session.
packets.Clear();
var replaced = route with { SendButtonAsync = (page, code, phase, guard) =>
{
    packets.Add(phase);
    live = false;
    return Task.CompletedTask;
} };
try { await DeviceSystemShortcuts.SendAsync(replaced, "home", () => true, default); throw new Exception("Replacement ignored"); }
catch (OperationCanceledException) { }
Check(packets.SequenceEqual(new[] { "down" }), "Cleanup reached replacement session");
live = true;
packets.Clear();
try { await DeviceSystemShortcuts.SendAsync(route, "arbitrary", () => true, default); throw new Exception("Invalid action accepted"); }
catch (AutomationException e) { Check(e.Code == "INVALID_REQUEST", "Wrong invalid-action error"); }
Check(packets.Count == 0, "Invalid action sent input");
var unsupported = route with { SendButtonAsync = null };
try { await DeviceSystemShortcuts.SendAsync(unsupported, "home", () => true, default); throw new Exception("Missing route accepted"); }
catch (AutomationException e) { Check(e.Code == "CAPABILITY_NOT_SUPPORTED", "Wrong unsupported error"); }
var bleCalls = new List<string>();
var ble = unsupported with { SendShortcutAsync = (name, guard) =>
{
    Check(guard(), "Bluetooth guard failed");
    bleCalls.Add(name);
    return Task.CompletedTask;
} };
await DeviceSystemShortcuts.SendAsync(ble, "app_switcher", () => true, default);
Check(bleCalls.SequenceEqual(new[] { "app_switcher" }), "Bluetooth route was not used exactly once");
Console.WriteLine("PASS nine actions, double Home, Globe cleanup, cancellation, uncertain failure, session replacement, validation and Bluetooth dispatch");

// Minimal transport contracts for isolated device-free tests. The complete native
// app build separately checks these calls against the real application types.
namespace IPhoneMirror.App.Services
{
    internal sealed record DirectKeyboardRoute(Func<bool> IsCurrent,
        Func<byte, IReadOnlyCollection<byte>, Func<bool>?, Task> SendAsync,
        Func<ushort, ushort, string, Func<bool>?, Task>? SendButtonAsync = null,
        Func<string, Func<bool>, Task>? SendShortcutAsync = null);
    internal static class CoreDeviceTouchProtocol
    {
        public const ushort IndigoConsumerUsagePage = 0x0C, IndigoHome = 0x40,
            IndigoSiri = 0xCF, IndigoVolumeUp = 0xE9, IndigoVolumeDown = 0xEA,
            IndigoLock = 0x30, GlobeKeyboardLayoutUsage = 0x029D;
    }
}
namespace IPhoneMirror.App.Services.Automation
{
    internal sealed class AutomationException(string code, string message, int status = 409) : Exception(message)
    {
        internal string Code { get; } = code;
        internal int Status { get; } = status;
    }
}
