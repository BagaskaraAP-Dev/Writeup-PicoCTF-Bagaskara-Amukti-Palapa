param(
    [string]$DesignPath = (Join-Path $PSScriptRoot 'VirtualMachine1.dae'),
    [string]$OutputPath = (Join-Path $PSScriptRoot 'machine.png')
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Xml.Linq
Add-Type -ReferencedAssemblies System.Drawing,System.Xml.Linq,System.Xml,System.Core -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Globalization;
using System.Linq;
using System.Xml.Linq;

public static class CtfModelRenderer {
    class Face {
        public PointF[] Points;
        public float Depth;
        public Color Color;
    }
    static double[] Numbers(string text) {
        return text.Split((char[])null, StringSplitOptions.RemoveEmptyEntries)
            .Select(s => double.Parse(s, CultureInfo.InvariantCulture)).ToArray();
    }
    static PointF Project(double[] p) {
        return new PointF((float)(p[0] + 0.22*p[1]), (float)(0.82*p[1] - 0.65*p[2]));
    }
    public static void Render(string source, string output) {
        XNamespace ns = "http://www.collada.org/2005/11/COLLADASchema";
        var doc = XDocument.Load(source);
        var meshes = doc.Descendants(ns+"geometry").ToDictionary(
            e => "#"+(string)e.Attribute("id"), e => e.Element(ns+"mesh"));
        var faces = new List<Face>();
        foreach (var node in doc.Descendants(ns+"visual_scene").Elements(ns+"node")) {
            var inst = node.Element(ns+"instance_geometry");
            var mesh = meshes[(string)inst.Attribute("url")];
            var raw = Numbers(mesh.Elements(ns+"source").First().Element(ns+"float_array").Value);
            var matrix = Numbers(node.Element(ns+"matrix").Value);
            var positions = new List<double[]>();
            for (int i=0; i<raw.Length; i+=3) {
                positions.Add(new double[] {
                    matrix[0]*raw[i]+matrix[1]*raw[i+1]+matrix[2]*raw[i+2]+matrix[3],
                    matrix[4]*raw[i]+matrix[5]*raw[i+1]+matrix[6]*raw[i+2]+matrix[7],
                    matrix[8]*raw[i]+matrix[9]*raw[i+1]+matrix[10]*raw[i+2]+matrix[11]
                });
            }
            string material = (string)inst.Descendants(ns+"instance_material").First().Attribute("target");
            Color baseColor = material.Contains("#Red-") ? Color.FromArgb(211,52,63) :
                material.Contains("#Blue-") ? Color.FromArgb(40,99,215) : Color.FromArgb(134,154,156);
            foreach (var triangles in mesh.Elements(ns+"triangles")) {
                var inputs = triangles.Elements(ns+"input").ToList();
                int stride = inputs.Max(e => (int?)e.Attribute("offset") ?? 0)+1;
                int offset = (int?)inputs.First(e => (string)e.Attribute("semantic")=="VERTEX").Attribute("offset") ?? 0;
                var ids = Numbers(triangles.Element(ns+"p").Value);
                for (int i=0; i<ids.Length; i+=stride*3) {
                    var a=positions[(int)ids[i+offset]];
                    var b=positions[(int)ids[i+stride+offset]];
                    var c=positions[(int)ids[i+stride*2+offset]];
                    double ux=b[0]-a[0], uy=b[1]-a[1], uz=b[2]-a[2];
                    double vx=c[0]-a[0], vy=c[1]-a[1], vz=c[2]-a[2];
                    double nx=uy*vz-uz*vy, ny=uz*vx-ux*vz, nz=ux*vy-uy*vx;
                    double norm=Math.Sqrt(nx*nx+ny*ny+nz*nz);
                    double shade=norm<0.00001 ? 0.8 : 0.48+0.52*Math.Abs((0.3*nx-0.4*ny+0.866*nz)/norm);
                    faces.Add(new Face {
                        Points=new PointF[] {Project(a),Project(b),Project(c)},
                        Depth=(float)((-0.22*(a[0]+b[0]+c[0])+(a[1]+b[1]+c[1])+1.27*(a[2]+b[2]+c[2]))/3.0),
                        Color=Color.FromArgb((int)(baseColor.R*shade),(int)(baseColor.G*shade),(int)(baseColor.B*shade))
                    });
                }
            }
        }
        float minX=faces.Min(f=>f.Points.Min(p=>p.X)), maxX=faces.Max(f=>f.Points.Max(p=>p.X));
        float minY=faces.Min(f=>f.Points.Min(p=>p.Y)), maxY=faces.Max(f=>f.Points.Max(p=>p.Y));
        float scale=Math.Min(1080/(maxX-minX),1760/(maxY-minY));
        using(var bitmap=new Bitmap(1200,1920))
        using(var g=Graphics.FromImage(bitmap)) {
            g.Clear(Color.White);
            g.SmoothingMode=SmoothingMode.AntiAlias;
            using(var font=new Font("Segoe UI",22,FontStyle.Bold))
                g.DrawString("Virtual Machine 1 | input: red, output: blue",font,Brushes.Black,32,20);
            foreach(var face in faces.OrderBy(f=>f.Depth)) {
                var pts=face.Points.Select(p=>new PointF(60+(p.X-minX)*scale,100+(p.Y-minY)*scale)).ToArray();
                using(var brush=new SolidBrush(face.Color)) g.FillPolygon(brush,pts);
            }
            bitmap.Save(output,System.Drawing.Imaging.ImageFormat.Png);
        }
    }
}
'@

[CtfModelRenderer]::Render($DesignPath, $OutputPath)
Get-Item -LiteralPath $OutputPath | Select-Object FullName, Length
