from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Q, Count, Avg
from django.http import JsonResponse
from .models import Categoria, Estabelecimento, Evento, Avaliacao
from .forms import RegistroForm, LoginForm, AvaliacaoForm
import json


def home(request):
    """Página inicial com categorias e estabelecimentos"""
    categorias = Categoria.objects.filter(ativo=True)
    categoria_selecionada_slug = request.GET.get('categoria')
    categoria_selecionada = None

    estabelecimentos = Estabelecimento.objects.filter(
        ativo=True).select_related('categoria')

    if categoria_selecionada_slug:
        estabelecimentos = estabelecimentos.filter(
            categoria__slug=categoria_selecionada_slug)
        try:
            categoria_selecionada = Categoria.objects.get(
                slug=categoria_selecionada_slug, ativo=True)
        except Categoria.DoesNotExist:
            pass

    # Adicionar média de avaliações
    estabelecimentos = estabelecimentos.annotate(
        media_avaliacoes=Avg('avaliacoes__estrelas'),
        total_avaliacoes=Count('avaliacoes')
    )

    context = {
        'categorias': categorias,
        'estabelecimentos': estabelecimentos,
        'categoria_selecionada': categoria_selecionada,
        'categoria_selecionada_slug': categoria_selecionada_slug,
    }
    return render(request, 'core/home.html', context)


def estabelecimento_detalhe(request, id):
    """Detalhes de um estabelecimento"""
    estabelecimento = get_object_or_404(
        Estabelecimento.objects.select_related(
            'categoria').prefetch_related('fotos', 'avaliacoes__usuario'),
        id=id,
        ativo=True
    )

    # Verificar se está nos favoritos do usuário
    is_favorito = False
    if request.user.is_authenticated:
        is_favorito = estabelecimento.favoritos.filter(
            id=request.user.id).exists()

    # Calcular média de avaliações
    avaliacoes = estabelecimento.avaliacoes.all()
    media_avaliacoes = avaliacoes.aggregate(
        Avg('estrelas'))['estrelas__avg'] or 0

    # Formulário de avaliação
    avaliacao_form = None
    usuario_ja_avaliou = False
    if request.user.is_authenticated:
        usuario_ja_avaliou = avaliacoes.filter(usuario=request.user).exists()
        if not usuario_ja_avaliou:
            avaliacao_form = AvaliacaoForm()

    context = {
        'estabelecimento': estabelecimento,
        'is_favorito': is_favorito,
        'avaliacoes': avaliacoes,
        'media_avaliacoes': round(media_avaliacoes, 1),
        'avaliacao_form': avaliacao_form,
        'usuario_ja_avaliou': usuario_ja_avaliou,
    }
    return render(request, 'core/estabelecimento_detalhe.html', context)


def eventos(request):
    """Lista de eventos"""
    tipo_selecionado = request.GET.get('tipo')

    eventos_list = Evento.objects.filter(ativo=True)

    if tipo_selecionado:
        eventos_list = eventos_list.filter(tipo=tipo_selecionado)

    context = {
        'eventos': eventos_list,
        'tipo_selecionado': tipo_selecionado,
        'tipos': Evento.TIPO_CHOICES,
    }
    return render(request, 'core/eventos.html', context)


def evento_detalhe(request, id):
    """Detalhes de um evento"""
    evento = get_object_or_404(Evento, id=id, ativo=True)

    context = {
        'evento': evento,
    }
    return render(request, 'core/evento_detalhe.html', context)


def mapa_interativo(request):
    """Mapa interativo com todos os estabelecimentos"""
    categoria_filtro = request.GET.get('categoria')

    estabelecimentos = Estabelecimento.objects.filter(
        ativo=True,
        latitude__isnull=False,
        longitude__isnull=False
    ).select_related('categoria').annotate(
        media_avaliacoes=Avg('avaliacoes__estrelas'),
        total_avaliacoes=Count('avaliacoes')
    )

    if categoria_filtro:
        estabelecimentos = estabelecimentos.filter(
            categoria__slug=categoria_filtro)

    categorias = Categoria.objects.filter(ativo=True)

    # Converter estabelecimentos para JSON para o mapa
    estabelecimentos_json = []
    for est in estabelecimentos:
        estabelecimentos_json.append({
            'id': est.id,
            'nome': est.nome,
            'categoria': est.categoria.nome,
            'endereco': est.endereco,
            'latitude': float(est.latitude),
            'longitude': float(est.longitude),
            'imagem': est.imagem_principal.url if est.imagem_principal else '',
            'descricao': est.descricao[:200] + '...' if len(est.descricao) > 200 else est.descricao,
            'horario': est.horario_funcionamento,
            'media_avaliacoes': round(est.media_avaliacoes or 0, 1),
        })

    context = {
        'estabelecimentos': estabelecimentos,
        'estabelecimentos_json': json.dumps(estabelecimentos_json),
        'categorias': categorias,
        'categoria_filtro': categoria_filtro,
    }
    return render(request, 'core/mapa_interativo.html', context)


def registro_view(request):
    """Registro de novos usuários"""
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(
                request, 'Conta criada com sucesso! Bem-vindo ao Minha Vitrine.')
            return redirect('home')
    else:
        form = RegistroForm()

    return render(request, 'core/registro.html', {'form': form})


def login_view(request):
    """Login de usuários"""
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                messages.success(
                    request, f'Bem-vindo de volta, {user.first_name or user.username}!')
                next_url = request.GET.get('next', 'home')
                return redirect(next_url)
            else:
                messages.error(request, 'Login ou senha incorretos.')
    else:
        form = LoginForm()

    return render(request, 'core/login.html', {'form': form})


@login_required
def logout_view(request):
    """Logout de usuários"""
    logout(request)
    messages.info(request, 'Você saiu da sua conta.')
    return redirect('home')


@login_required
def favoritar_estabelecimento(request, id):
    """Adicionar/remover estabelecimento dos favoritos"""
    estabelecimento = get_object_or_404(Estabelecimento, id=id)

    if request.user in estabelecimento.favoritos.all():
        estabelecimento.favoritos.remove(request.user)
        is_favorito = False
        mensagem = 'Estabelecimento removido dos favoritos'
    else:
        estabelecimento.favoritos.add(request.user)
        is_favorito = True
        mensagem = 'Estabelecimento adicionado aos favoritos'

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'is_favorito': is_favorito,
            'total_favoritos': estabelecimento.total_favoritos(),
            'mensagem': mensagem
        })

    messages.success(request, mensagem)
    return redirect('estabelecimento_detalhe', id=id)


@login_required
def meus_favoritos(request):
    """Lista de estabelecimentos favoritos do usuário"""
    estabelecimentos = request.user.estabelecimentos_favoritos.filter(
        ativo=True
    ).select_related('categoria').annotate(
        media_avaliacoes=Avg('avaliacoes__estrelas'),
        total_avaliacoes=Count('avaliacoes')
    )

    context = {
        'estabelecimentos': estabelecimentos,
    }
    return render(request, 'core/favoritos.html', context)


@login_required
def avaliar_estabelecimento(request, id):
    """Avaliar um estabelecimento"""
    estabelecimento = get_object_or_404(Estabelecimento, id=id)

    # Verificar se já avaliou
    if Avaliacao.objects.filter(estabelecimento=estabelecimento, usuario=request.user).exists():
        messages.warning(request, 'Você já avaliou este estabelecimento.')
        return redirect('estabelecimento_detalhe', id=id)

    if request.method == 'POST':
        form = AvaliacaoForm(request.POST)
        if form.is_valid():
            avaliacao = form.save(commit=False)
            avaliacao.estabelecimento = estabelecimento
            avaliacao.usuario = request.user
            avaliacao.save()
            messages.success(request, 'Avaliação enviada com sucesso!')
            return redirect('estabelecimento_detalhe', id=id)

    return redirect('estabelecimento_detalhe', id=id)


def buscar(request):
    """Busca de estabelecimentos e eventos"""
    query = request.GET.get('q', '')
    categoria = request.GET.get('categoria')

    estabelecimentos = Estabelecimento.objects.filter(ativo=True)

    if query:
        estabelecimentos = estabelecimentos.filter(
            Q(nome__icontains=query) |
            Q(descricao__icontains=query) |
            Q(endereco__icontains=query)
        )

    if categoria:
        estabelecimentos = estabelecimentos.filter(categoria__slug=categoria)

    estabelecimentos = estabelecimentos.select_related('categoria').annotate(
        media_avaliacoes=Avg('avaliacoes__estrelas'),
        total_avaliacoes=Count('avaliacoes')
    )

    context = {
        'estabelecimentos': estabelecimentos,
        'query': query,
        'categoria_selecionada': categoria,
    }
    return render(request, 'core/busca.html', context)
