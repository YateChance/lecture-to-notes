from course_context import LESSON_ROOT, LESSON, MODEL_PATH, MODEL_CACHE
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root=LESSON_ROOT;out=root/'08_report/assets';out.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none','figure.facecolor':'white'})
stable='#167466';unstable='#bd5a35'
fig,axes=plt.subplots(2,2,figsize=(11,8),layout='constrained')
def base(ax,title):
 ax.axhline(0,color='#d6dddb',lw=.8);ax.axvline(0,color='#d6dddb',lw=.8)
 ax.set(xlabel='$r$',ylabel='$x^*$',title=title,xlim=(-1.05,1.05),ylim=(-1.25,1.25));ax.grid(alpha=.12)
r=np.linspace(-1,0,300);rp=np.linspace(0,1,300)
ax=axes[0,0];base(ax,'Saddle-node: $\\dot x=r+x^2$')
ax.plot(r,-np.sqrt(-r),color=stable,lw=2.5,label='Stable');ax.plot(r,np.sqrt(-r),color=unstable,ls='--',lw=2.5,label='Unstable');ax.plot(0,0,'o',color='#334a45',ms=5);ax.legend(frameon=False,fontsize=9)
ax=axes[0,1];base(ax,'Transcritical: $\\dot x=rx-x^2$')
ax.plot(r,np.zeros_like(r),color=stable,lw=2.5);ax.plot(rp,np.zeros_like(rp),color=unstable,ls='--',lw=2.5);ax.plot(r,r,color=unstable,ls='--',lw=2.5);ax.plot(rp,rp,color=stable,lw=2.5)
ax=axes[1,0];base(ax,'Supercritical pitchfork: $\\dot x=rx-x^3$')
ax.plot(r,np.zeros_like(r),color=stable,lw=2.5);ax.plot(rp,np.zeros_like(rp),color=unstable,ls='--',lw=2.5)
for sign in [-1,1]:ax.plot(rp,sign*np.sqrt(rp),color=stable,lw=2.5)
ax=axes[1,1];base(ax,'Subcritical pitchfork: $\\dot x=rx+x^3$')
ax.plot(r,np.zeros_like(r),color=stable,lw=2.5);ax.plot(rp,np.zeros_like(rp),color=unstable,ls='--',lw=2.5)
for sign in [-1,1]:ax.plot(r,sign*np.sqrt(-r),color=unstable,ls='--',lw=2.5)
fig.savefig(out/'bifurcations.svg');fig.savefig(out/'bifurcations.png',dpi=180);plt.close(fig)

fig,axes=plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
r=np.linspace(0,1.6,400);h=2/(3*np.sqrt(3))*r**1.5
ax=axes[0];ax.fill_between(r,-h,h,color='#dbede7');ax.plot(r,h,color=stable,lw=2);ax.plot(r,-h,color=stable,lw=2)
ax.set(xlabel='$r$',ylabel='$h$',title='Parameter plane: $\\dot x=h+rx-x^3$')
ax.text(.9,0,'3 equilibria\n2 stable + 1 unstable',ha='center',va='center',fontsize=10);ax.text(.3,.55,'1 stable equilibrium',fontsize=10);ax.grid(alpha=.12)
ax=axes[1];c=1/np.sqrt(3);xs=np.linspace(-1.6,1.6,1000)
for lo,hi,st in [(-1.6,-c,True),(-c,c,False),(c,1.6,True)]:
 x=np.linspace(lo,hi,400);ax.plot(x**3-x,x,color=stable if st else unstable,lw=2.5,ls='-' if st else '--')
hc=2/(3*np.sqrt(3));ax.axvline(hc,color='#a9b8b3',ls=':',lw=1);ax.axvline(-hc,color='#a9b8b3',ls=':',lw=1)
ax.annotate('',xy=(hc,2*c),xytext=(hc,-c),arrowprops={'arrowstyle':'->','color':'#506e88','lw':2})
ax.annotate('',xy=(-hc,-2*c),xytext=(-hc,c),arrowprops={'arrowstyle':'->','color':'#506e88','lw':2})
ax.set(xlabel='$h$',ylabel='$x^*$',title='Stable branches and jumps at $r=1$',xlim=(-1,1),ylim=(-1.5,1.5));ax.grid(alpha=.12)
fig.savefig(out/'hysteresis.svg');fig.savefig(out/'hysteresis.png',dpi=180);plt.close(fig)
print('Generated bifurcations and hysteresis figures')
