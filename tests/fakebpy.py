"""A fake `bpy`: enough Blender to execute generated migration code.

Standard library only. Blender is not in this environment and never will be on
a CI runner, but the generator's output is ordinary Python -- so it can be run,
and running it is the only way most of these defects show themselves. Four of
them are invisible to a fake that merely accepts whatever it is given, so those
four behaviours are modelled deliberately:

* **float32.** Blender stores floats as float32; the snapshot carries the
  float64 that JSON round-trips. Assign 0.01 and read back 0.009999999776482582.
  Without this, defect 8 cannot happen here and the idempotence tests are
  decoration.
* **Read-only properties raise AttributeError**, not TypeError. That difference
  is defect 2: catching only TypeError killed a whole run.
* **Enums validate, and some depend on another property.** `look` depends on
  `view_transform`, which depends on `display_device`; `file_format` depends on
  `media_type`. Refusals raise TypeError, which the generated code catches and
  logs as "skipped" -- exactly how defect 5 stayed invisible.
* **Pointer properties refuse a string.** Assigning "ACEScg" to
  `linear_colorspace_settings` raises TypeError; it has to go to `.name`.
  That is defect 3, and it silently cost ACEScg twice.

What it does NOT model, and cannot: screens being freed, undo pushes,
notifier queues, redo panels, the window manager. The three defects that live
there (9, 10, 11) are Blender's own memory management, and no fake reproduces
a use-after-free. Their tests say so in their own docstrings.
"""

import struct
import sys
import types

CANCELLED = {'CANCELLED'}
FINISHED = {'FINISHED'}


def as_float32(value):
    """What Blender's storage does to a float64 on the way in."""
    return struct.unpack("f", struct.pack("f", value))[0]


# --- the property system ----------------------------------------------------

class Prop:
    """One RNA property: a default, and what assigning to it does."""

    def __init__(self, default, readonly=False):
        self.default = default
        self.readonly = readonly

    def coerce(self, owner, value):
        return value


class Float(Prop):
    def coerce(self, owner, value):
        if isinstance(value, str):
            raise TypeError("expected a float, not str")
        return as_float32(float(value))


class Int(Prop):
    def coerce(self, owner, value):
        if isinstance(value, (str, float)):
            raise TypeError("expected an int, not %s" % type(value).__name__)
        return int(value)


class Bool(Prop):
    def coerce(self, owner, value):
        if not isinstance(value, bool):
            raise TypeError("expected a bool, not %s" % type(value).__name__)
        return value


class String(Prop):
    def coerce(self, owner, value):
        if not isinstance(value, str):
            raise TypeError("expected a string, not %s" % type(value).__name__)
        return value


class Enum(Prop):
    """`items` is a tuple, or a callable taking the owning struct.

    The callable form is the point: in Blender the set of valid values often
    depends on another property that must therefore be written first.
    """

    def __init__(self, default, items, readonly=False):
        Prop.__init__(self, default, readonly)
        self.items = items

    def allowed(self, owner):
        return tuple(self.items(owner) if callable(self.items) else self.items)

    def coerce(self, owner, value):
        allowed = self.allowed(owner)
        if value not in allowed:
            # Blender's own wording, and its own exception type. gen_scene_prop
            # catches TypeError and logs "skipped".
            raise TypeError("enum %r not found in %r" % (value, allowed))
        return value


class Pointer(Prop):
    """A struct-valued property. Assigning anything else raises TypeError."""

    def __init__(self, factory, expects=None, readonly=True):
        Prop.__init__(self, None, readonly)
        self.factory = factory
        self.expects = expects

    def coerce(self, owner, value):
        if self.expects is not None and value is not None:
            if not isinstance(value, self.expects):
                raise TypeError("expected a %s type, not %s"
                                % (self.expects.__name__, type(value).__name__))
        return value


class RNAStruct:
    """Attributes are declared or they do not exist -- as in RNA.

    Setting an undeclared attribute raises AttributeError rather than quietly
    creating one. A fake that accepts anything would let a generator writing to
    a property that no longer exists pass every test.
    """

    props = {}

    def __init__(self, **overrides):
        object.__setattr__(self, "_values", {})
        for name, prop in self.props.items():
            if isinstance(prop, Pointer):
                self._values[name] = prop.factory() if prop.factory else None
            else:
                self._values[name] = prop.default
        for name, value in overrides.items():
            self.force(name, value)

    def force(self, name, value):
        """Set up the starting state, ignoring read-only. Not for code under test."""
        if name not in self.props:
            raise AttributeError("no such property to set up: %r" % name)
        self._values[name] = value
        return self

    def __getattr__(self, name):
        try:
            return object.__getattribute__(self, "_values")[name]
        except KeyError:
            raise AttributeError('bpy_struct: attribute "%s" not found' % name)

    def __setattr__(self, name, value):
        prop = self.props.get(name)
        if prop is None:
            raise AttributeError('bpy_struct: attribute "%s" not found' % name)
        if prop.readonly:
            raise AttributeError('bpy_struct: attribute "%s" is read-only' % name)
        self._values[name] = prop.coerce(self, value)


class ID(RNAStruct):
    """A datablock: it has a name and it carries custom ID properties."""

    # use_fake_user is on every ID in Blender, and the workspace deletion needs
    # it: dropping the fake user and purging is the third route it tries.
    props = {"name": String(""), "use_fake_user": Bool(False)}

    def __init__(self, name="", **overrides):
        RNAStruct.__init__(self, **overrides)
        self._values["name"] = name
        object.__setattr__(self, "_id_props", {})

    def __getitem__(self, key):
        return self._id_props[key]

    def __setitem__(self, key, value):
        self._id_props[key] = value

    def get(self, key, default=None):
        return self._id_props.get(key, default)

    def __repr__(self):
        return "<%s %r>" % (type(self).__name__, self.name)


class Collection:
    """bpy_prop_collection: iterable, indexable by name, with .get()."""

    def __init__(self, items=()):
        self._items = list(items)

    def get(self, key, default=None):
        if not isinstance(key, (str, tuple)):
            # The real message, because the generated code once hit it: passing
            # the list that libraries.load() filled in place.
            raise TypeError("key must be a string or tuple, not %s"
                            % type(key).__name__)
        for item in self._items:
            if item.name == key:
                return item
        return default

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._items[key]
        found = self.get(key)
        if found is None:
            raise KeyError(key)
        return found

    def __iter__(self):
        return iter(list(self._items))

    def __len__(self):
        return len(self._items)

    def __contains__(self, key):
        return self.get(key) is not None

    def add(self, item):
        self._items.append(item)
        return item

    def discard(self, item):
        if item in self._items:
            self._items.remove(item)

    def names(self):
        return [item.name for item in self._items]


# --- colour management ------------------------------------------------------

DISPLAY_DEVICES = ('sRGB', 'Rec.1886', 'Display P3')

# The documented chain, modelled: which view transforms exist depends on the
# display device, and which looks exist depends on the view transform.
VIEW_TRANSFORMS = {
    'sRGB': ('Standard', 'AgX', 'Filmic', 'Khronos PBR Neutral'),
    'Rec.1886': ('Standard', 'Filmic'),
    'Display P3': ('Standard', 'AgX'),
}
LOOKS = {
    'Standard': ('None',),
    'AgX': ('None', 'AgX - Punchy', 'AgX - Base Contrast', 'AgX - Greyscale'),
    'Filmic': ('None', 'Filmic - High Contrast'),
    'Khronos PBR Neutral': ('None',),
}


class ColorspaceSettings(RNAStruct):
    """A struct that reads like a string in a snapshot -- but is not one."""

    props = {"name": Enum('sRGB', ('sRGB', 'Linear Rec.709', 'ACEScg',
                                   'Non-Color', 'Filmic Log'))}


class ImageFormatSettings(RNAStruct):
    props = {
        "media_type": Enum('IMAGE', ('IMAGE', 'MULTI_LAYER_IMAGE', 'VIDEO')),
        # While media_type is IMAGE there is no OPEN_EXR_MULTILAYER in the enum
        # at all. That is what made writing the format first fail silently.
        "file_format": Enum('PNG', lambda owner: (
            ('OPEN_EXR_MULTILAYER',) if owner.media_type == 'MULTI_LAYER_IMAGE'
            else ('AVIF', 'BMP', 'JPEG', 'OPEN_EXR', 'PNG', 'TIFF'))),
        "color_depth": Enum('8', lambda owner: (
            ('16', '32') if owner.file_format.startswith('OPEN_EXR')
            else ('8', '16'))),
        "exr_codec": Enum('ZIP', ('NONE', 'PXR24', 'ZIP', 'PIZ', 'DWAA')),
        "linear_colorspace_settings": Pointer(ColorspaceSettings,
                                              expects=ColorspaceSettings),
        # Derived from file_format, and read-only in 5.2 -- the dumper skips it.
        "has_linear_colorspace": Bool(False, readonly=True),
    }


class RenderSettings(RNAStruct):
    props = {
        "filepath": String("//"),
        "resolution_x": Int(1920),
        "resolution_y": Int(1080),
        "resolution_percentage": Int(100),
        "engine": Enum('BLENDER_EEVEE_NEXT',
                       ('BLENDER_EEVEE_NEXT', 'CYCLES', 'BLENDER_WORKBENCH')),
        "film_transparent": Bool(False),
        "image_settings": Pointer(ImageFormatSettings),
        # Derived from image_settings.file_format, read-only in 5.2.
        "file_extension": String(".png", readonly=True),
    }


class ViewSettings(RNAStruct):
    props = {
        "view_transform": Enum('Standard',
                               lambda owner: VIEW_TRANSFORMS.get(
                                   owner._display.display_device, ('Standard',))),
        "look": Enum('None',
                     lambda owner: LOOKS.get(owner.view_transform, ('None',))),
        "exposure": Float(0.0),
        "gamma": Float(1.0),
        "use_curve_mapping": Bool(False),
    }

    def __init__(self, display, **overrides):
        # The dependency is a real one in Blender: the enum is rebuilt from the
        # display device. Holding the reference is how the fake reproduces it.
        object.__setattr__(self, "_display", display)
        RNAStruct.__init__(self, **overrides)


class DisplaySettings(RNAStruct):
    props = {"display_device": Enum('sRGB', DISPLAY_DEVICES)}


class UnitSettings(RNAStruct):
    props = {
        "system": Enum('METRIC', ('NONE', 'METRIC', 'IMPERIAL')),
        "scale_length": Float(1.0),
    }


class CyclesSettings(RNAStruct):
    props = {
        "samples": Int(128),
        "use_denoising": Bool(True),
        "denoising_use_gpu": Bool(False),
    }


class EeveeSettings(RNAStruct):
    props = {
        "taa_render_samples": Int(64),
        "use_raytracing": Bool(False),
    }


# --- objects and scenes -----------------------------------------------------

class Object(ID):
    props = dict(ID.props, **{
        "type": String('EMPTY'),
        "hide_viewport": Bool(False),
        "hide_render": Bool(False),
        "empty_display_size": Float(1.0),
        # The datablock, not a name. Renames go through obj.data.name, because
        # the ".001" suffixes depend on load order and differ between copies.
        "data": Pointer(lambda: None, readonly=False),
    })


class DOFSettings(RNAStruct):
    props = {
        "use_dof": Bool(False),
        "focus_object": Pointer(lambda: None, expects=Object, readonly=False),
        "focus_distance": Float(10.0),
        "aperture_fstop": Float(2.8),
    }


class CameraData(ID):
    props = dict(ID.props, **{
        "lens": Float(50.0),
        "sensor_width": Float(36.0),
        "clip_start": Float(0.1),
        "clip_end": Float(100.0),
        "dof": Pointer(DOFSettings),
    })


class SceneCollection(ID):
    props = dict(ID.props, **{
        "color_tag": Enum('NONE', tuple(['NONE'] + ['COLOR_%02d' % n
                                                    for n in range(1, 9)])),
        "hide_viewport": Bool(False),
        "hide_render": Bool(False),
    })


class Scene(ID):
    props = dict(ID.props, **{
        "render": Pointer(RenderSettings),
        "view_settings": Pointer(None),          # built in __init__, see below
        "display_settings": Pointer(DisplaySettings),
        "unit_settings": Pointer(UnitSettings),
        "cycles": Pointer(CyclesSettings),
        "eevee": Pointer(EeveeSettings),
        "sequencer_colorspace_settings": Pointer(ColorspaceSettings),
        "compositing_node_group": Pointer(lambda: None, readonly=False),
        "frame_start": Int(1),
        "frame_end": Int(250),
    })

    def __init__(self, name="Scene", **overrides):
        ID.__init__(self, name, **overrides)
        display = self._values["display_settings"]
        self._values["view_settings"] = ViewSettings(display)


# --- compositor -------------------------------------------------------------

class Socket:
    def __init__(self, identifier, default_value=None):
        self.identifier = identifier
        self.default_value = default_value


class Node:
    def __init__(self, node_type, name="", inputs=("Image",),
                 outputs=("Image",)):
        self.type = node_type
        self.name = name
        self.label = ""
        self.mute = False
        self.location = (0.0, 0.0)
        self.node_tree = None
        self.inputs = [Socket(i) for i in inputs]
        self.outputs = [Socket(o) for o in outputs]

    def __repr__(self):
        return "<Node %r>" % self.name


class Nodes(Collection):
    """tree.nodes -- with new() and remove(), which the generated code uses."""

    def __init__(self, items=(), sockets=None):
        Collection.__init__(self, items)
        # identifier lists per node type, so a fixture can describe real nodes
        self.sockets = sockets or {}

    def new(self, node_type):
        inputs, outputs = self.sockets.get(node_type, (("Image",), ("Image",)))
        node = Node(node_type, name=node_type, inputs=inputs, outputs=outputs)
        self.add(node)
        return node

    def remove(self, node):
        self.discard(node)


class Link:
    def __init__(self, from_socket, from_node, to_socket, to_node):
        self.from_socket = from_socket
        self.from_node = from_node
        self.to_socket = to_socket
        self.to_node = to_node


class Links:
    def __init__(self, tree):
        self._tree = tree
        self._items = []

    def __iter__(self):
        return iter(list(self._items))

    def __len__(self):
        return len(self._items)

    def new(self, out_socket, in_socket):
        from_node = self._tree.node_of(out_socket)
        to_node = self._tree.node_of(in_socket)
        link = Link(out_socket, from_node, in_socket, to_node)
        self._items.append(link)
        return link

    def remove(self, link):
        if link in self._items:
            self._items.remove(link)

    def as_tuples(self):
        return sorted((l.from_node.name, l.from_socket.identifier,
                       l.to_node.name, l.to_socket.identifier)
                      for l in self._items)


class NodeTree(ID):
    props = dict(ID.props)

    def __init__(self, name="Compositing", nodes=(), sockets=None):
        ID.__init__(self, name)
        object.__setattr__(self, "nodes", Nodes(nodes, sockets))
        object.__setattr__(self, "links", Links(self))

    def node_of(self, socket):
        for node in self.nodes:
            if socket in node.inputs or socket in node.outputs:
                return node
        raise LookupError("socket belongs to no node in this tree")


# --- interface --------------------------------------------------------------

class Region:
    def __init__(self, region_type='WINDOW'):
        self.type = region_type
        self.active_panel_category = ""


class Space:
    def __init__(self, space_type, **kwargs):
        self.type = space_type
        self.image = None
        for key, value in kwargs.items():
            setattr(self, key, value)


class Area:
    def __init__(self, area_type, spaces=None, regions=None):
        self.type = area_type
        self.spaces = spaces if spaces is not None else [Space(area_type)]
        self.regions = regions if regions is not None else [Region('WINDOW')]


class Screen(ID):
    def __init__(self, name="Screen", areas=()):
        ID.__init__(self, name)
        object.__setattr__(self, "areas", list(areas))


class WorkSpace(ID):
    props = dict(ID.props)

    def __init__(self, name="Layout", screens=()):
        ID.__init__(self, name)
        object.__setattr__(self, "screens", list(screens) or [Screen(name + "-s")])


class Window:
    def __init__(self, workspace=None, screen=None):
        self.workspace = workspace
        self.screen = screen


class Image(ID):
    props = dict(ID.props, **{"size": Prop((256, 256))})


# --- the module-level fakes -------------------------------------------------

class Libraries:
    """bpy.data.libraries.load() -- including filling data_to in place.

    The in-place fill is modelled because it caused a real bug: handing load()
    the same list the names were kept in turned that list into datablocks and
    workspaces.get() then raised "key must be a string or tuple, not WorkSpace".
    """

    def __init__(self, data):
        self._data = data
        self.workspaces_in_file = []
        self.node_groups_in_file = []
        self.loaded_paths = []
        # A name here comes back as None from load(): the "%d of %d came
        # through" branch.
        self.refuse = set()

    def unique(self, name):
        """What Blender does when the name is taken: append .001.

        Not decoration -- it is the whole reason the generated code renames the
        existing workspace aside first. Without it a test could not tell a
        replacement from a duplicate, which is the failure being guarded.
        """
        if self._data.workspaces.get(name) is None:
            return name
        for number in range(1, 1000):
            candidate = "%s.%03d" % (name, number)
            if self._data.workspaces.get(candidate) is None:
                return candidate
        raise RuntimeError("no free name for %r" % name)

    def load(self, path, link=False):
        self.loaded_paths.append(path)
        libraries = self

        class Source:
            workspaces = list(libraries.workspaces_in_file)
            node_groups = list(libraries.node_groups_in_file)

        class Target:
            workspaces = []
            node_groups = []

        class Loader:
            def __enter__(self):
                return Source, Target

            def __exit__(self, *exc):
                # Blender replaces the requested names with the datablocks it
                # appended, in place, on the way out.
                appended = []
                for name in Target.workspaces:
                    if name in libraries.refuse:
                        appended.append(None)
                        continue
                    workspace = WorkSpace(libraries.unique(name))
                    libraries._data.workspaces.add(workspace)
                    appended.append(workspace)
                Target.workspaces = appended
                groups = []
                for name in Target.node_groups:
                    group = NodeTree(name)
                    libraries._data.node_groups.add(group)
                    groups.append(group)
                Target.node_groups = groups
                return False

        return Loader()


class Colorspace(RNAStruct):
    """bpy.data.colorspace -- a property of the FILE, and read-only."""

    props = {"working_space": Enum('Linear Rec.709',
                                   ('Linear Rec.709', 'Linear Rec.2020',
                                    'ACEScg'),
                                   readonly=True)}


class CameraCollection(Collection):
    def new(self, name):
        return self.add(CameraData(name))


class ObjectCollection(Collection):
    def new(self, name, data=None):
        kind = 'CAMERA' if isinstance(data, CameraData) else 'EMPTY'
        obj = Object(name, type=kind)
        obj.data = data
        return self.add(obj)


class Data:
    def __init__(self):
        self.scenes = Collection()
        self.objects = ObjectCollection()
        self.cameras = CameraCollection()
        self.collections = Collection()
        self.images = Collection()
        self.node_groups = Collection()
        self.workspaces = Collection()
        self.texts = Collection()
        self.materials = Collection()
        self.colorspace = Colorspace()
        self.libraries = Libraries(self)
        self.removed = []
        self.purges = 0
        # Where the .blend sits. The interface step writes its log next to it,
        # so a test must point this somewhere it owns.
        self.filepath = ""

    def batch_remove(self, ids):
        for item in ids:
            self.removed.append(item)
            for collection in (self.workspaces, self.objects, self.cameras,
                               self.collections, self.texts):
                collection.discard(item)

    def orphans_purge(self, do_local_ids=True, do_recursive=False):
        self.purges += 1
        return 0


class Context:
    def __init__(self, scene=None, window=None):
        self.scene = scene
        self.window = window
        self.workspace = window.workspace if window else None
        self.area = None
        self.region = None
        self.overrides = []

    def temp_override(self, **kwargs):
        context = self

        class Override:
            def __enter__(self):
                self.previous = {k: getattr(context, k, None) for k in kwargs}
                context.overrides.append(dict(kwargs))
                for key, value in kwargs.items():
                    setattr(context, key, value)
                return context

            def __exit__(self, *exc):
                for key, value in self.previous.items():
                    setattr(context, key, value)
                return False

        return Override()


class Operator:
    def __init__(self, ops, name):
        self._ops = ops
        self._name = name

    def __call__(self, *args, **kwargs):
        self._ops.calls.append((self._name, args, kwargs))
        handler = self._ops.handlers.get(self._name)
        if handler is None:
            # The default is the one that cost a release: an operator that
            # declines does it silently. "No exception" is not evidence.
            return CANCELLED
        return handler(self._ops.bpy, *args, **kwargs) or FINISHED


class OpsNamespace:
    def __init__(self, ops, prefix):
        self._ops = ops
        self._prefix = prefix

    def __getattr__(self, name):
        return Operator(self._ops, "%s.%s" % (self._prefix, name))


class Ops:
    def __init__(self, bpy):
        self.bpy = bpy
        self.calls = []
        self.handlers = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return OpsNamespace(self, name)

    def called(self, name):
        return [call for call in self.calls if call[0] == name]


class Timers:
    """bpy.app.timers, with the firing under the test's control.

    Nothing here runs by itself. A test asserts what has happened when the
    script returns -- that is the whole question for defects 9 and 10 -- and
    then fires the queue by hand.
    """

    def __init__(self):
        self.registered = []

    def register(self, function, first_interval=0.0, persistent=False):
        self.registered.append((function, first_interval))

    def is_registered(self, function):
        return any(f is function for f, _i in self.registered)

    def fire(self, rounds=200):
        """Run every registered timer to completion. Returns how many ran."""
        ran = 0
        queue = list(self.registered)
        self.registered = []
        while queue and rounds > 0:
            rounds -= 1
            function, _interval = queue.pop(0)
            result = function()
            ran += 1
            if isinstance(result, (int, float)):
                queue.append((function, result))
            # Anything registered while this one ran joins the queue.
            queue.extend(self.registered)
            self.registered = []
        if rounds <= 0:
            raise AssertionError("timers never settled -- a callback keeps "
                                 "rescheduling itself")
        return ran


class App:
    def __init__(self):
        self.timers = Timers()
        self.version = (5, 2, 0)


class Utils:
    def __init__(self):
        self.resources = {}

    def system_resource(self, kind, path=""):
        return self.resources.get((kind, path))


def make(scene=None, window=None):
    """A fresh fake bpy module. Never shared between tests."""
    module = types.ModuleType("bpy")
    module.data = Data()
    module.app = App()
    module.utils = Utils()
    module.ops = Ops(module)
    scene = scene if scene is not None else Scene()
    module.data.scenes.add(scene)
    module.context = Context(scene=scene, window=window)
    module.types = types.SimpleNamespace(Operator=object, Panel=object,
                                         AddonPreferences=object)
    module.props = types.SimpleNamespace()
    return module


class installed:
    """Context manager: put a fake bpy in sys.modules for the duration."""

    def __init__(self, module):
        self.module = module

    def __enter__(self):
        self.previous = sys.modules.get("bpy")
        sys.modules["bpy"] = self.module
        return self.module

    def __exit__(self, *exc):
        if self.previous is None:
            sys.modules.pop("bpy", None)
        else:
            sys.modules["bpy"] = self.previous
        return False
